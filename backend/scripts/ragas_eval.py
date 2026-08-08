"""RAGAS evaluation harness against the labor-law gold set (LEG-86/87).

Runs the gold set in evals/labor_law_gold_set.json against the real
company-hosted embedding/LLM API — no fakes, same spirit as
scripts/smoke_test_rag.py.

Two pipelines can be measured, which is the point of --mode both:

    direct  RetrievalService -> AnswerService, the straight-line path that
            /query/ask used before LEG-80.
    graph   The LangGraph (route -> retrieve|reason -> answer -> cite) that
            RagService.ask() runs now. Invoked directly with AllCases()
            rather than through RagService, so no user/assignment fixtures
            are needed — RagService only adds authorisation resolution and
            the citation filename lookup, neither of which affects quality.

Two layers of checking, because the gold set was written for both:

1. Deterministic checks the gold set's own fields were designed for
   (see the "notes" field on each item, which call out substring collisions
   to watch for): did retrieval surface the expected article, and does the
   generated answer contain one of the expected substrings.
2. RAGAS metrics that need no reference answer — faithfulness (is the answer
   actually grounded in the retrieved passages, not the model's own
   training) and answer_relevancy (does the answer address the question
   asked). Gold-set items only carry expected substrings/sections, not full
   reference answers, so context_recall/answer_correctness (which need a
   ground_truth string) are deliberately left out — a substring is not a
   reference answer, and scoring against one would just measure how closely
   the model's phrasing happens to match a snippet.

## Why --repeat exists (LEG-87)

This pipeline is not deterministic, and the gold set is small. Two runs of
*identical* code have flipped 6 of the 15 items. A single run therefore
measures the run, not the system, and a difference between two single runs
is not evidence of anything.

--repeat N runs the whole set N times and reports each rate as a mean with
its spread across those rounds, plus which items changed their verdict
between rounds. Read the spread before reading the mean: if the spread
covers the difference you care about, you have not measured it. Items listed
as unstable are the ones making it wide, and are where extra gold-set work
pays off.

## What lands where

    evals/results/<stamp>-<mode>.json   every item, every round, in full.
                                        Gitignored — large, and mostly the
                                        Arabic answer text.
    evals/history.jsonl                 one line per run, tracked in git.
                                        This is the durable record.
    docs/eval-results.md                generated from history.jsonl by
                                        scripts/eval_report.py.

Runs are also traced to Langfuse when it is configured (LEG-83/84): one span
per gold-set item, carrying the deterministic verdicts as scores, and the
RAGAS grades attached afterwards against the same trace. Without Langfuse
configured the harness behaves identically and traces nothing.

Requires the `evals` optional dependency group (not installed by default):
    uv sync --extra evals

Usage:
    uv run python scripts/ragas_eval.py                    # both pipelines, compared
    uv run python scripts/ragas_eval.py --mode graph       # just the live path
    uv run python scripts/ragas_eval.py --repeat 3         # measure the spread
    uv run python scripts/ragas_eval.py --skip-ragas       # deterministic checks only
    uv run python scripts/ragas_eval.py --top-k 3

Needs COMPANY_API_URL/COMPANY_API_KEY set in backend/.env and the dev
Postgres/pgvector container running, with the full labor-law corpus already
ingested (fetch_hrsd_labor_law.py + the ingestion worker, or an equivalent
seed) — this script only reads, it does not seed data.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

if hasattr(sys.stdout, "reconfigure"):
    # Guarded so this module can be imported under pytest, whose replacement
    # stdout has no reconfigure. The console still needs it: Windows defaults
    # to cp1252 and the gold set is Arabic.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlmodel import Session, create_engine  # noqa: E402

from embeddings.company_api import CompanyEmbeddingProvider  # noqa: E402
from foundation.authorization import AllCases  # noqa: E402
from foundation.models import DocumentChunk  # noqa: E402
from graph.builder import build_graph  # noqa: E402
from graph.state import GraphState  # noqa: E402
from observability import build_tracer  # noqa: E402
from observability.tracer import Kind, Observation, Tracer  # noqa: E402
from repositories.document_chunk_repository import DocumentChunkRepository  # noqa: E402
from services.answer_service import AnswerService  # noqa: E402
from services.company_llm import CompanyLLMProvider  # noqa: E402
from services.retrieval_service import RetrievalService, unique_passages  # noqa: E402

DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/legalmind"
GOLD_SET_PATH = Path(__file__).resolve().parent.parent / "evals" / "labor_law_gold_set.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "evals" / "results"
HISTORY_PATH = Path(__file__).resolve().parent.parent / "evals" / "history.jsonl"

RATE_KEYS = ("context_hit_rate", "answer_hit_rate", "answered_rate")
QUALITY_KEYS = ("mean_faithfulness", "mean_answer_relevancy")


class CollectingTracer(Tracer):
    """Forwards everything to a real tracer, and keeps a running token tally.

    The harness needs token counts, but it does not make the model calls —
    the providers do, several layers down, and each one reports its usage on
    its own `Observation`. Wrapping the tracer is what lets those counts be
    read without the harness reaching into the providers or the providers
    knowing an eval is running.
    """

    def __init__(self, inner: Tracer) -> None:
        self._inner = inner
        self.tokens: Counter[str] = Counter()

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        kind: Kind = Kind.SPAN,
        input: Any = None,
        model: str | None = None,
    ) -> Iterator[Observation]:
        with self._inner.observe(name, kind=kind, input=input, model=model) as record:
            try:
                yield record
            finally:
                # The provider fills `usage` before its own block exits, which
                # is inside this one — so by here it is final. Empty for spans
                # that are not model calls, and Counter.update ignores those.
                self.tokens.update(record.usage)

    def score(
        self,
        name: str,
        value: float,
        *,
        comment: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._inner.score(name, value, comment=comment, trace_id=trace_id)

    def flush(self) -> None:
        self._inner.flush()


@dataclass
class ItemResult:
    id: str
    lang: str
    question: str
    expected_section: str
    expected_answer_contains: list[str]
    answered: bool
    answer_text: str
    contexts: list[str]
    context_hit: bool  # expected_section text turned up somewhere in the top-k retrieval
    answer_hit: bool  # answer contains one of the expected substrings
    notes: str

    # Graph-only diagnostics. None on the direct path, which has no router.
    route: str | None = None
    iterations: int | None = None
    reasoning: list[str] = field(default_factory=list)
    duplicate_passages_avoided: int = 0
    """How many repeats the dedup removed before the model saw them — i.e. what
    a plain flatten of `context_chunks` would have sent twice. Overlapping
    matches in one document share neighbours, so this is normally non-zero; it
    is the work the dedup is doing, not a defect count."""

    # LEG-87. "Cost" on a self-hosted gateway is these two, not a price.
    latency_ms: int = 0
    tokens: dict[str, int] = field(default_factory=dict)

    trace_id: str | None = None
    """Which Langfuse trace this item produced, so RAGAS can score it once the
    whole batch has been graded. None when tracing is not configured."""

    round_index: int = 0
    """Which pass of --repeat this result came from. Items with the same id and
    different verdicts across rounds are what `unstable_items` reports."""


def _build_services(
    session: Session, tracer: Tracer
) -> tuple[RetrievalService, AnswerService, CompanyLLMProvider]:
    llm = CompanyLLMProvider(tracer=tracer)
    retrieval = RetrievalService(
        chunks=DocumentChunkRepository(session),
        embedding_provider=CompanyEmbeddingProvider(tracer=tracer),
    )
    return retrieval, AnswerService(llm), llm


def _score_item(
    item: dict, retrieved_text: str, answer, passages: list[DocumentChunk], raw_count: int
) -> dict:
    """The two deterministic checks, plus how much the dedup removed.

    `passages` is what the model actually saw; `raw_count` is what a plain
    flatten would have handed it. The difference is the dedup's work.
    """
    return {
        "context_hit": item["expected_section"] in retrieved_text,
        "answer_hit": bool(answer)
        and answer.answered
        and any(needle in answer.text for needle in item["expected_answer_contains"]),
        "duplicate_passages_avoided": raw_count - len(passages),
    }


@contextmanager
def _observed_item(
    tracer: CollectingTracer, item: dict, mode: str, round_index: int
) -> Iterator[dict]:
    """One span per gold-set item, timed, with its tokens attributed to it.

    Yields a dict the caller fills in with the verdicts. Everything the model
    does for this item nests inside this span, exactly as the provider spans
    nest inside `rag-run` in production (LEG-84) — so an eval item reads in
    Langfuse the same way a real question does.
    """
    before = Counter(tracer.tokens)
    started = time.perf_counter()

    outcome: dict[str, Any] = {}
    with tracer.observe(
        f"eval-item[{mode}]",
        kind=Kind.SPAN,
        input={"question": item["question"]},
    ) as record:
        record.metadata.update(
            {"gold_item": item["id"], "lang": item["lang"], "mode": mode, "round": round_index}
        )
        try:
            yield outcome
        finally:
            outcome["latency_ms"] = int((time.perf_counter() - started) * 1000)
            outcome["tokens"] = dict(tracer.tokens - before)
            outcome["trace_id"] = record.trace_id

            record.output = {
                "context_hit": outcome.get("context_hit"),
                "answer_hit": outcome.get("answer_hit"),
                "answered": outcome.get("answered"),
            }
            record.metadata["latency_ms"] = outcome["latency_ms"]

            # Scored inside the block, against the span that is still open.
            # The RAGAS grades cannot be: they need the whole batch answered
            # first, and arrive later via trace_id.
            for name in ("context_hit", "answer_hit", "answered"):
                if name in outcome:
                    tracer.score(name, float(bool(outcome[name])))


def run_direct(
    session: Session, gold_set: dict, top_k: int, tracer: CollectingTracer, round_index: int
) -> list[ItemResult]:
    """The pre-LEG-80 path: retrieve, dedupe, answer."""
    retrieval, answers, _ = _build_services(session, tracer)

    results = []
    for item in gold_set["items"]:
        with _observed_item(tracer, item, "direct", round_index) as outcome:
            matches = retrieval.retrieve(item["question"], within=AllCases(), top_k=top_k)
            passages = unique_passages(matches)
            answer = answers.answer(item["question"], passages)

            raw_count = sum(len(m.context_chunks) for m in matches)
            scored = _score_item(
                item, "\n".join(m.match.text for m in matches), answer, passages, raw_count
            )
            outcome.update(scored)
            outcome["answered"] = answer.answered

        results.append(
            ItemResult(
                id=item["id"],
                lang=item["lang"],
                question=item["question"],
                expected_section=item["expected_section"],
                expected_answer_contains=item["expected_answer_contains"],
                answered=answer.answered,
                answer_text=answer.text,
                contexts=[p.text for p in passages],
                notes=item.get("notes", ""),
                latency_ms=outcome["latency_ms"],
                tokens=outcome["tokens"],
                trace_id=outcome["trace_id"],
                round_index=round_index,
                **scored,
            )
        )
        print(f"  [direct] {item['id']}: ctx={scored['context_hit']} ans={scored['answer_hit']}")

    return results


def run_graph(
    session: Session, gold_set: dict, top_k: int, tracer: CollectingTracer, round_index: int
) -> list[ItemResult]:
    """The live path: the compiled LangGraph, exactly as RagService.ask runs it.

    top_k is not plumbed through the graph — the retrieve node uses
    RetrievalService's own default. Passed here only so the two modes report
    the same parameter; a non-default value applies to the direct run only.
    """
    retrieval, answers, llm = _build_services(session, tracer)
    graph = build_graph(llm, retrieval, answers)

    results = []
    for item in gold_set["items"]:
        with _observed_item(tracer, item, "graph", round_index) as outcome:
            final = graph.invoke(GraphState(question=item["question"], authorized=AllCases()))

            answer = final.get("answer")
            matches = final.get("matches", [])

            # The same set the answer node built, so `contexts` reflects what the
            # model was actually prompted with rather than a pre-dedup flatten.
            passages = unique_passages(matches)
            raw_count = sum(len(m.context_chunks) for m in matches)

            scored = _score_item(
                item, "\n".join(m.match.text for m in matches), answer, passages, raw_count
            )
            route = final.get("route")
            outcome.update(scored)
            outcome["answered"] = bool(answer and answer.answered)

        results.append(
            ItemResult(
                id=item["id"],
                lang=item["lang"],
                question=item["question"],
                expected_section=item["expected_section"],
                expected_answer_contains=item["expected_answer_contains"],
                answered=bool(answer and answer.answered),
                answer_text=answer.text if answer else "",
                contexts=[p.text for p in passages],
                notes=item.get("notes", ""),
                route=str(route) if route else None,
                iterations=final.get("iterations", 0),
                reasoning=list(final.get("reasoning", [])),
                latency_ms=outcome["latency_ms"],
                tokens=outcome["tokens"],
                trace_id=outcome["trace_id"],
                round_index=round_index,
                **scored,
            )
        )
        print(
            f"  [graph]  {item['id']}: ctx={scored['context_hit']} "
            f"ans={scored['answer_hit']} route={route}"
        )

    return results


def _stub_missing_vertexai_imports() -> None:
    """ragas.llms.base eagerly imports langchain_community's Vertex AI
    integration at module load time, even though nothing here uses it.
    Recent langchain-community releases split that integration out into
    the separate langchain-google-vertexai package, so the bare import
    ModuleNotFoundErrors before ragas is even usable — unless that ~28
    package Google Cloud SDK is installed for a provider we never call.
    Stub the two symbols ragas imports (never instantiated) instead.
    """
    import sys
    import types

    if "langchain_community.chat_models.vertexai" not in sys.modules:
        stub = types.ModuleType("langchain_community.chat_models.vertexai")
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules["langchain_community.chat_models.vertexai"] = stub

    import langchain_community.llms as llms_module

    if not hasattr(llms_module, "VertexAI"):
        llms_module.VertexAI = type("VertexAI", (), {})


def run_ragas(results: list[ItemResult], label: str, tracer: Tracer) -> dict[str, dict[str, float]]:
    """LLM-graded faithfulness + answer_relevancy, scored via the same
    company gateway used for answering (it's OpenAI-compatible, so
    langchain-openai talks to it directly — no custom wrapper needed).

    Returns {item_id: {"faithfulness": ..., "answer_relevancy": ...}}.
    Unanswered items are skipped: there is no answer for RAGAS to grade.

    Grades are also pushed back to each item's Langfuse trace (LEG-87). That
    has to happen here rather than inside the run: RAGAS grades a batch, and
    the batch is only complete once every span has closed.
    """
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    _stub_missing_vertexai_imports()
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    gradeable = [r for r in results if r.answered and r.contexts]
    if not gradeable:
        print(f"[{label}] nothing answered — skipping RAGAS (nothing to grade).")
        return {}

    dataset = Dataset.from_list(
        [
            {"question": r.question, "answer": r.answer_text, "contexts": r.contexts}
            for r in gradeable
        ]
    )

    base_url = f"{os.environ['COMPANY_API_URL'].rstrip('/')}/v1"
    llm = ChatOpenAI(
        base_url=base_url,
        api_key=os.environ["COMPANY_API_KEY"],
        model=os.environ.get("COMPANY_LLM_MODEL", "gemma4"),
        temperature=0,
    )
    # OpenAIEmbeddings defaults to text-embedding-ada-002, which the company
    # gateway doesn't serve (confirmed: it 400s). Must name the same model
    # CompanyEmbeddingProvider implicitly relies on the gateway defaulting to.
    embeddings = OpenAIEmbeddings(
        base_url=base_url,
        api_key=os.environ["COMPANY_API_KEY"],
        model=os.environ.get("COMPANY_EMBEDDING_MODEL", "bge-m3"),
    )

    scored = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        embeddings=embeddings,
    ).to_pandas()

    graded = {}
    for i, r in enumerate(gradeable):
        item_scores = {
            "faithfulness": float(scored.iloc[i]["faithfulness"]),
            "answer_relevancy": float(scored.iloc[i]["answer_relevancy"]),
        }
        graded[r.id] = item_scores

        if r.trace_id:
            for name, value in item_scores.items():
                # NaN is RAGAS declining to grade, not a zero. Sending it would
                # drag every average in the UI down with a number nobody meant.
                if value == value:
                    tracer.score(name, value, trace_id=r.trace_id)

    return graded


def summarise(results: list[ItemResult], ragas_scores: dict[str, dict[str, float]]) -> dict:
    latencies = [r.latency_ms for r in results]
    tokens: Counter[str] = Counter()
    for r in results:
        tokens.update(r.tokens)

    return {
        "total": len(results),
        "context_hit_rate": _rate(results, lambda r: r.context_hit),
        "answer_hit_rate": _rate(results, lambda r: r.answer_hit),
        "answered_rate": _rate(results, lambda r: r.answered),
        "mean_faithfulness": _mean(ragas_scores, "faithfulness"),
        "mean_answer_relevancy": _mean(ragas_scores, "answer_relevancy"),
        # How many items that mean actually covers. RAGAS times out on some
        # items and returns NaN, so a mean can silently describe half the set
        # — and observed here, the half it drops is the Arabic half.
        "faithfulness_graded": _graded(ragas_scores, "faithfulness"),
        "answer_relevancy_graded": _graded(ragas_scores, "answer_relevancy"),
        "multi_step_routed": sum(1 for r in results if r.route and "multi_step" in r.route.lower()),
        "duplicates_avoided": sum(r.duplicate_passages_avoided for r in results),
        "mean_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "tokens": dict(tokens),
    }


def spread(values: list[float]) -> dict[str, float]:
    """Mean and how far the rounds disagreed, for one metric.

    `stdev` needs two rounds; with one there is no spread to report and None
    says so, where 0.0 would claim the metric was stable when it was simply
    never measured twice.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return {"mean": None, "stdev": None, "min": None, "max": None, "rounds": 0}

    return {
        "mean": round(statistics.mean(clean), 3),
        "stdev": round(statistics.stdev(clean), 3) if len(clean) > 1 else None,
        "min": round(min(clean), 3),
        "max": round(max(clean), 3),
        "rounds": len(clean),
    }


def unstable_items(rounds: list[list[ItemResult]]) -> list[str]:
    """Gold-set items that did not give the same verdict every round.

    The single most important number in a run with --repeat: these are the
    items making the spread wide, and no comparison narrower than that spread
    means anything until they are fixed or removed.
    """
    if len(rounds) < 2:
        return []

    verdicts: dict[str, set[tuple[bool, bool]]] = {}
    for results in rounds:
        for r in results:
            verdicts.setdefault(r.id, set()).add((r.context_hit, r.answer_hit))

    return sorted(item_id for item_id, seen in verdicts.items() if len(seen) > 1)


def answers_repeated_exactly(rounds: list[list[ItemResult]]) -> bool | None:
    """Whether every item returned byte-identical text in every round.

    The check that stops --repeat being read as more than it is. The provider
    pins `temperature: 0` (services/company_llm.py), so for one prompt against
    one corpus the model has no freedom to answer differently — and when this
    is True, the rounds re-ran a deterministic path and a spread of 0.0 says
    nothing about how stable the *system* is.

    That makes a True here the interesting result, not a reassuring one: it
    means repeating is not the way to find this pipeline's instability, and
    whatever made the gold set flip 6 of 15 items previously lives somewhere
    a repeat cannot reach — a different route, model, or corpus state.

    None when there is only one round, which measured nothing either way.
    """
    if len(rounds) < 2:
        return None

    texts: dict[str, set[str]] = {}
    for results in rounds:
        for r in results:
            texts.setdefault(r.id, set()).add(r.answer_text)

    return all(len(seen) == 1 for seen in texts.values())


def aggregate(rounds: list[list[ItemResult]], summaries: list[dict]) -> dict:
    """Roll the per-round summaries into one set of mean ± spread figures."""
    aggregated: dict[str, Any] = {
        "rounds": len(summaries),
        "total": summaries[0]["total"] if summaries else 0,
        "unstable_items": unstable_items(rounds),
        "answers_repeated_exactly": answers_repeated_exactly(rounds),
    }

    for key in RATE_KEYS + QUALITY_KEYS:
        aggregated[key] = spread([s[key] for s in summaries])

    tokens: Counter[str] = Counter()
    for s in summaries:
        tokens.update(s["tokens"])

    for key in ("faithfulness_graded", "answer_relevancy_graded"):
        aggregated[key] = int(statistics.mean([s[key] for s in summaries])) if summaries else 0

    aggregated["mean_latency_ms"] = int(statistics.mean([s["mean_latency_ms"] for s in summaries]))
    aggregated["max_latency_ms"] = max(s["max_latency_ms"] for s in summaries)
    aggregated["total_tokens"] = dict(tokens)
    aggregated["duplicates_avoided"] = sum(s["duplicates_avoided"] for s in summaries)
    aggregated["multi_step_routed"] = sum(s["multi_step_routed"] for s in summaries)
    return aggregated


def git_sha() -> str | None:
    """Which commit produced these numbers. Without it the history is a list
    of scores nobody can attribute to a change."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_report(
    mode: str,
    rounds: list[list[ItemResult]],
    ragas_scores: list[dict[str, dict[str, float]]],
    stamp: str,
    aggregated: dict,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{stamp}-{mode}.json"

    payload = {
        "gold_set": str(GOLD_SET_PATH),
        "mode": mode,
        "run_at": datetime.now().isoformat(),
        "git_sha": git_sha(),
        "rounds": [
            [{**vars(r), **ragas_scores[i].get(r.id, {})} for r in results]
            for i, results in enumerate(rounds)
        ],
        "summary": aggregated,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def append_history(mode: str, stamp: str, aggregated: dict, args: argparse.Namespace) -> None:
    """One line per run, appended to a tracked file.

    JSONL rather than a rewritten JSON array so two runs can never lose each
    other's line, and so a diff of this file shows exactly the run that was
    added. This — not evals/results/, which is gitignored — is what makes
    quality visible over time.
    """
    entry = {
        "stamp": stamp,
        "mode": mode,
        "git_sha": git_sha(),
        "llm_model": os.environ.get("COMPANY_LLM_MODEL", "gemma4"),
        "embedding_model": os.environ.get("COMPANY_EMBEDDING_MODEL", "bge-m3"),
        "multi_step": os.environ.get("RAG_MULTI_STEP_ENABLED", ""),
        "top_k": args.top_k,
        "ragas": not args.skip_ragas,
        **aggregated,
    }

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _rate(results: list[ItemResult], predicate) -> float:
    return round(sum(1 for r in results if predicate(r)) / len(results), 3) if results else 0.0


def _mean(scores: dict[str, dict[str, float]], key: str) -> float | None:
    values = [s[key] for s in scores.values() if key in s and s[key] == s[key]]
    return round(sum(values) / len(values), 3) if values else None


def _graded(scores: dict[str, dict[str, float]], key: str) -> int:
    """How many items RAGAS actually returned a number for.

    `s[key] == s[key]` is a NaN test: RAGAS returns NaN when a grade times out
    or it declines to judge, and those items are absent from the mean. Without
    this count the mean looks like it describes the whole gold set.
    """
    return sum(1 for s in scores.values() if key in s and s[key] == s[key])


def _format_spread(stats: dict) -> str:
    if stats["mean"] is None:
        return "n/a"
    if stats["stdev"] is None:
        return f"{stats['mean']}"
    return f"{stats['mean']} ± {stats['stdev']}  (min {stats['min']}, max {stats['max']})"


def _print_summary(mode: str, aggregated: dict) -> None:
    print(f"\n--- {mode} ({aggregated['rounds']} round(s), {aggregated['total']} items) ---")
    for key in RATE_KEYS:
        print(f"  {key:24} {_format_spread(aggregated[key])}")
    for key in QUALITY_KEYS:
        graded = aggregated.get(f"{key.removeprefix('mean_')}_graded", 0)
        covers = f"  [graded {graded}/{aggregated['total']}]" if aggregated[key]["mean"] else ""
        print(f"  {key:24} {_format_spread(aggregated[key])}{covers}")
    print(f"  {'mean_latency_ms':24} {aggregated['mean_latency_ms']}")
    print(f"  {'max_latency_ms':24} {aggregated['max_latency_ms']}")
    print(f"  {'total_tokens':24} {aggregated['total_tokens'] or 'not reported'}")

    unstable = aggregated["unstable_items"]
    if unstable:
        print(f"\n  UNSTABLE across rounds ({len(unstable)}/{aggregated['total']}):")
        for item_id in unstable:
            print(f"    - {item_id}")
        print("  Any difference smaller than the spread above is noise, not a result.")
    elif aggregated["answers_repeated_exactly"]:
        print(
            f"\n  every round returned byte-identical answers ({aggregated['rounds']} rounds).\n"
            "  This path is deterministic (temperature 0), so the rounds re-ran the same\n"
            "  computation — a spread of 0.0 here is not evidence the system is stable."
        )
    elif aggregated["rounds"] > 1:
        print(f"\n  every item gave the same verdict in all {aggregated['rounds']} rounds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=["direct", "graph", "both"],
        default="both",
        help="which pipeline to measure (default: both, and print a comparison)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "run the whole gold set this many times and report mean +/- spread. "
            "Two rounds of identical code have flipped 6 of 15 items, so a single "
            "round is not a measurement of the system"
        ),
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="run only the deterministic section/substring checks, skip LLM-graded RAGAS metrics",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    gold_set = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))
    engine = create_engine(DATABASE_URL)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"

    tracer = CollectingTracer(build_tracer())

    modes = ["direct", "graph"] if args.mode == "both" else [args.mode]
    runners = {"direct": run_direct, "graph": run_graph}
    aggregates: dict[str, dict] = {}

    for mode in modes:
        rounds: list[list[ItemResult]] = []
        per_round_scores: list[dict[str, dict[str, float]]] = []
        per_round_summaries: list[dict] = []

        for round_index in range(args.repeat):
            print(
                f"\nRunning {len(gold_set['items'])} gold-set questions "
                f"[{mode}] round {round_index + 1}/{args.repeat}..."
            )
            with Session(engine) as session:
                results = runners[mode](session, gold_set, args.top_k, tracer, round_index)

            scores = {} if args.skip_ragas else run_ragas(results, mode, tracer)

            rounds.append(results)
            per_round_scores.append(scores)
            per_round_summaries.append(summarise(results, scores))

        aggregated = aggregate(rounds, per_round_summaries)
        out_path = write_report(mode, rounds, per_round_scores, stamp, aggregated)
        append_history(mode, stamp, aggregated, args)
        aggregates[mode] = aggregated
        print(f"wrote {out_path}")

    # Buffered in a background thread; a short-lived script must ask.
    tracer.flush()

    for mode, aggregated in aggregates.items():
        _print_summary(mode, aggregated)

    if len(aggregates) == 2:
        print("\n--- direct -> graph ---")
        for key in RATE_KEYS + QUALITY_KEYS:
            before, after = aggregates["direct"][key], aggregates["graph"][key]
            if before["mean"] is None or after["mean"] is None:
                continue

            delta = round(after["mean"] - before["mean"], 3)
            # The widest spread either side showed. A delta inside it is not a
            # difference between the pipelines, it is the same noise twice.
            noise = max(s["stdev"] or 0.0 for s in (before, after))
            verdict = "NOISE" if abs(delta) <= noise else "outside spread"
            print(f"  {key:24} {before['mean']} -> {after['mean']}  ({delta:+}) {verdict}")

        if aggregates["direct"]["rounds"] < 2:
            print("  (single round — no spread to judge against. Re-run with --repeat 3.)")

    print(f"\nappended {len(aggregates)} run(s) to {HISTORY_PATH}")
    print("regenerate the tracked report with: uv run python scripts/eval_report.py")
    print("\n(Arabic answers are in the JSON reports — read those with a file viewer.)")


if __name__ == "__main__":
    main()
