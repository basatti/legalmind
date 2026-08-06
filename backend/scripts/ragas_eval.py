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

Requires the `evals` optional dependency group (not installed by default):
    uv sync --extra evals

Usage:
    uv run python scripts/ragas_eval.py                    # both pipelines, compared
    uv run python scripts/ragas_eval.py --mode graph       # just the live path
    uv run python scripts/ragas_eval.py --skip-ragas       # deterministic checks only
    uv run python scripts/ragas_eval.py --top-k 3

Needs COMPANY_API_URL/COMPANY_API_KEY set in backend/.env and the dev
Postgres/pgvector container running, with the full labor-law corpus already
ingested (fetch_hrsd_labor_law.py + the ingestion worker, or an equivalent
seed) — this script only reads, it does not seed data.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlmodel import Session, create_engine  # noqa: E402

from embeddings.company_api import CompanyEmbeddingProvider  # noqa: E402
from foundation.authorization import AllCases  # noqa: E402
from foundation.models import DocumentChunk  # noqa: E402
from graph.builder import build_graph  # noqa: E402
from graph.state import GraphState  # noqa: E402
from repositories.document_chunk_repository import DocumentChunkRepository  # noqa: E402
from services.answer_service import AnswerService  # noqa: E402
from services.company_llm import CompanyLLMProvider  # noqa: E402
from services.retrieval_service import RetrievalService, unique_passages  # noqa: E402

DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/legalmind"
GOLD_SET_PATH = Path(__file__).resolve().parent.parent / "evals" / "labor_law_gold_set.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "evals" / "results"


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


def _build_services(session: Session) -> tuple[RetrievalService, AnswerService, CompanyLLMProvider]:
    llm = CompanyLLMProvider()
    retrieval = RetrievalService(
        chunks=DocumentChunkRepository(session),
        embedding_provider=CompanyEmbeddingProvider(),
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
        "answer_hit": answer.answered
        and any(needle in answer.text for needle in item["expected_answer_contains"]),
        "duplicate_passages_avoided": raw_count - len(passages),
    }


def run_direct(session: Session, gold_set: dict, top_k: int) -> list[ItemResult]:
    """The pre-LEG-80 path: retrieve, dedupe, answer."""
    retrieval, answers, _ = _build_services(session)

    results = []
    for item in gold_set["items"]:
        matches = retrieval.retrieve(item["question"], within=AllCases(), top_k=top_k)
        passages = unique_passages(matches)
        answer = answers.answer(item["question"], passages)

        raw_count = sum(len(m.context_chunks) for m in matches)
        scored = _score_item(
            item, "\n".join(m.match.text for m in matches), answer, passages, raw_count
        )
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
                **scored,
            )
        )
        print(f"  [direct] {item['id']}: ctx={scored['context_hit']} ans={scored['answer_hit']}")

    return results


def run_graph(session: Session, gold_set: dict, top_k: int) -> list[ItemResult]:
    """The live path: the compiled LangGraph, exactly as RagService.ask runs it.

    top_k is not plumbed through the graph — the retrieve node uses
    RetrievalService's own default. Passed here only so the two modes report
    the same parameter; a non-default value applies to the direct run only.
    """
    retrieval, answers, llm = _build_services(session)
    graph = build_graph(llm, retrieval, answers)

    results = []
    for item in gold_set["items"]:
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


def run_ragas(results: list[ItemResult], label: str) -> dict[str, dict[str, float]]:
    """LLM-graded faithfulness + answer_relevancy, scored via the same
    company gateway used for answering (it's OpenAI-compatible, so
    langchain-openai talks to it directly — no custom wrapper needed).

    Returns {item_id: {"faithfulness": ..., "answer_relevancy": ...}}.
    Unanswered items are skipped: there is no answer for RAGAS to grade.
    """
    import os

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
        model=os.environ.get("COMPANY_LLM_MODEL", "gpt-oss"),
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

    return {
        r.id: {
            "faithfulness": float(scored.iloc[i]["faithfulness"]),
            "answer_relevancy": float(scored.iloc[i]["answer_relevancy"]),
        }
        for i, r in enumerate(gradeable)
    }


def summarise(results: list[ItemResult], ragas_scores: dict[str, dict[str, float]]) -> dict:
    return {
        "total": len(results),
        "context_hit_rate": _rate(results, lambda r: r.context_hit),
        "answer_hit_rate": _rate(results, lambda r: r.answer_hit),
        "answered_rate": _rate(results, lambda r: r.answered),
        "mean_faithfulness": _mean(ragas_scores, "faithfulness"),
        "mean_answer_relevancy": _mean(ragas_scores, "answer_relevancy"),
        "multi_step_routed": sum(1 for r in results if r.route and "multi_step" in r.route.lower()),
        "duplicates_avoided": sum(r.duplicate_passages_avoided for r in results),
    }


def write_report(
    mode: str, results: list[ItemResult], ragas_scores: dict[str, dict[str, float]], stamp: str
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{stamp}-{mode}.json"

    payload = {
        "gold_set": str(GOLD_SET_PATH),
        "mode": mode,
        "run_at": datetime.now().isoformat(),
        "items": [{**vars(r), **ragas_scores.get(r.id, {})} for r in results],
        "summary": summarise(results, ragas_scores),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _rate(results: list[ItemResult], predicate) -> float:
    return round(sum(1 for r in results if predicate(r)) / len(results), 3) if results else 0.0


def _mean(scores: dict[str, dict[str, float]], key: str) -> float | None:
    values = [s[key] for s in scores.values() if key in s and s[key] == s[key]]
    return round(sum(values) / len(values), 3) if values else None


def _print_summary(mode: str, summary: dict) -> None:
    print(f"\n--- {mode} ---")
    for key, value in summary.items():
        print(f"  {key:28} {value}")


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
        "--skip-ragas",
        action="store_true",
        help="run only the deterministic section/substring checks, skip LLM-graded RAGAS metrics",
    )
    args = parser.parse_args()

    gold_set = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))
    engine = create_engine(DATABASE_URL)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"

    modes = ["direct", "graph"] if args.mode == "both" else [args.mode]
    runners = {"direct": run_direct, "graph": run_graph}
    summaries: dict[str, dict] = {}

    for mode in modes:
        print(f"\nRunning {len(gold_set['items'])} gold-set questions [{mode}]...")
        with Session(engine) as session:
            results = runners[mode](session, gold_set, args.top_k)

        scores = {} if args.skip_ragas else run_ragas(results, mode)
        out_path = write_report(mode, results, scores, stamp)
        summaries[mode] = summarise(results, scores)
        print(f"wrote {out_path}")

    for mode, summary in summaries.items():
        _print_summary(mode, summary)

    if len(summaries) == 2:
        print("\n--- direct -> graph ---")
        for key in summaries["direct"]:
            before, after = summaries["direct"][key], summaries["graph"][key]
            if isinstance(before, int | float) and isinstance(after, int | float):
                arrow = "same" if before == after else f"{before} -> {after}"
                print(f"  {key:28} {arrow}")

    print("\n(Arabic answers are in the JSON reports — read those with a file viewer.)")


if __name__ == "__main__":
    main()
