"""Turn evals/history.jsonl into docs/eval-results.md (LEG-87).

LEG-86 measures quality; this makes the measurement outlive the terminal it
was printed in. `ragas_eval.py` appends one line per run to a tracked JSONL
file, and this renders every line into a document that goes in git next to
the code it describes.

Two separations worth keeping:

- **History is data, the report is a view.** The JSONL is append-only and
  never rewritten, so a bad report can be regenerated and a run can never be
  edited away. Regenerating is always safe.
- **A figure never appears without what limits it.** Rates carry their spread;
  single-round runs are marked as measuring nothing; runs whose rounds came
  back byte-identical are marked deterministic rather than stable; and a RAGAS
  mean carries how many items it actually covers. Each of those was a way this
  report could have stated a true number that led to a false conclusion.

Usage:
    uv run python scripts/eval_report.py
    uv run python scripts/eval_report.py --history path --out path
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    # Guarded so this module can be imported under pytest, whose replacement
    # stdout has no reconfigure. The console still needs it: Windows defaults
    # to cp1252 and the gold set is Arabic.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = Path(__file__).resolve().parent.parent
HISTORY_PATH = BACKEND / "evals" / "history.jsonl"
REPORT_PATH = BACKEND.parent / "docs" / "eval-results.md"

RATE_KEYS = ("context_hit_rate", "answer_hit_rate", "answered_rate")
QUALITY_KEYS = ("mean_faithfulness", "mean_answer_relevancy")
ALL_KEYS = RATE_KEYS + QUALITY_KEYS

HEADINGS = {
    "context_hit_rate": "context hit",
    "answer_hit_rate": "answer hit",
    "answered_rate": "answered",
    "mean_faithfulness": "faithfulness",
    "mean_answer_relevancy": "relevancy",
}


def load_history(path: Path) -> list[dict[str, Any]]:
    """Every run ever recorded, oldest first.

    A malformed line is skipped rather than fatal: the file is append-only
    and a half-written line from an interrupted run must not make the whole
    history unreadable.
    """
    if not path.exists():
        return []

    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"skipping unreadable history line {number}", file=sys.stderr)

    return sorted(entries, key=lambda e: (e.get("stamp", ""), e.get("mode", "")))


def cell(entry: dict[str, Any], key: str) -> str:
    """One metric as `mean ± stdev`, or the mean alone when never repeated.

    RAGAS metrics also carry how many items they cover. RAGAS returns NaN when
    a grade times out, those items drop out of the mean, and a bare 0.917 that
    actually describes 8 of 15 items is worse than no number — observed, and
    the items it dropped were the Arabic ones.
    """
    stats = entry.get(key)
    if not isinstance(stats, dict) or stats.get("mean") is None:
        return "—"

    rendered = (
        f"{stats['mean']}" if stats.get("stdev") is None else f"{stats['mean']} ± {stats['stdev']}"
    )

    graded = entry.get(f"{key.removeprefix('mean_')}_graded")
    total = entry.get("total")
    if graded is not None and total and graded < total:
        rendered += f"<br>*({graded}/{total} graded)*"

    return rendered


def stability_cell(entry: dict[str, Any], unstable: list[str], total: int) -> str:
    """What the rounds established about stability — including "nothing".

    Three genuinely different states, and collapsing any two of them is how a
    report starts lying: one round never looked; several rounds that returned
    identical text looked at a deterministic path and learned nothing about
    the system; several rounds that diverged are the only case where a count
    of unstable items means what it appears to mean.
    """
    if entry.get("rounds", 1) < 2:
        return "not measured"
    if entry.get("answers_repeated_exactly"):
        return "deterministic"
    return f"{len(unstable)}/{total}"


def tokens_cell(entry: dict[str, Any]) -> str:
    total = entry.get("total_tokens") or {}
    if not total:
        return "—"
    if "total" in total:
        return f"{total['total']:,}"
    return f"{sum(total.values()):,}"


def render(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Evaluation results")
    add("")
    add("**Generated — do not edit by hand.**")
    add("Regenerate with `uv run python scripts/eval_report.py` from `backend/`.")
    add("")
    add("Source of truth is `backend/evals/history.jsonl`, one appended line per run of")
    add("`scripts/ragas_eval.py`. Per-item detail lives in `backend/evals/results/`, which")
    add("is gitignored — it is large and mostly Arabic answer text.")
    add("")

    if not entries:
        add("No runs recorded yet. Run `uv run python scripts/ragas_eval.py --repeat 3`.")
        add("")
        return "\n".join(lines)

    add("## How to read this")
    add("")
    add("Every rate is the mean across the rounds of one run, `±` its standard deviation.")
    add("**A difference smaller than the spread is not a result.** A run with no `±` is a")
    add("single round: it measures that run, not the system, and cannot support a")
    add("comparison at all.")
    add("")
    add("**A spread of `± 0.0` is not the same as a stable system.** The LLM provider pins")
    add("`temperature: 0`, so one prompt against one corpus produces one answer. Where a")
    add("run is marked *deterministic* below, every round returned byte-identical text —")
    add("the rounds re-ran the same computation, and agreeing with itself is the only")
    add("thing they could have done. Repeating is how you find that out; it is not, on")
    add("that evidence, a way to measure this pipeline's real variability.")
    add("")
    add("**A RAGAS metric marked `(n/total graded)` does not describe the whole gold set.**")
    add("RAGAS returns NaN when a grade times out and those items drop silently out of the")
    add("mean. This has been observed hitting the Arabic items specifically, which is the")
    add("half that matters most here — a high faithfulness score covering only the English")
    add("items is not a result about this system.")
    add("")
    add('"Cost" is tokens and latency. The company gateway is self-hosted, so there is no')
    add("vendor price to report and Langfuse's cost column is correctly $0.00 — see the")
    add('"A note on cost" section of `docs/observability.md`.')
    add("")

    add("## Runs")
    add("")
    header = ["run", "mode", "commit", "model", "rounds"]
    header += [HEADINGS[k] for k in ALL_KEYS]
    header += ["unstable", "mean ms", "tokens"]
    add("| " + " | ".join(header) + " |")
    add("|" + "|".join(["---"] * len(header)) + "|")

    for entry in reversed(entries):
        unstable = entry.get("unstable_items") or []
        total = entry.get("total", 0)
        row = [
            entry.get("stamp", "—"),
            entry.get("mode", "—"),
            entry.get("git_sha") or "—",
            entry.get("llm_model", "—"),
            str(entry.get("rounds", 1)),
        ]
        row += [cell(entry, key) for key in ALL_KEYS]
        row += [
            stability_cell(entry, unstable, total),
            str(entry.get("mean_latency_ms", "—")),
            tokens_cell(entry),
        ]
        add("| " + " | ".join(row) + " |")

    add("")

    latest = entries[-1]
    add("## Latest run")
    add("")
    add(
        f"`{latest.get('stamp')}` — mode `{latest.get('mode')}`, commit "
        f"`{latest.get('git_sha') or 'unknown'}`, model `{latest.get('llm_model')}`, "
        f"{latest.get('rounds', 1)} round(s), top-k {latest.get('top_k')}, "
        f"multi-step `{latest.get('multi_step') or 'off'}`."
    )
    add("")

    unstable = latest.get("unstable_items") or []
    if unstable:
        add(f"### Unstable items ({len(unstable)}/{latest.get('total', 0)})")
        add("")
        add("These gave different verdicts between rounds of the *same* code. They are what")
        add("makes the spread wide, and the first place to spend gold-set effort.")
        add("")
        for item_id in unstable:
            add(f"- `{item_id}`")
        add("")
    elif latest.get("answers_repeated_exactly"):
        add("### Deterministic — the rounds did not test anything")
        add("")
        add(f"All {latest['rounds']} rounds returned **byte-identical answer text** for every")
        add("item. At `temperature: 0` that is what a repeat of the same question against an")
        add("unchanged corpus has to do, so `± 0.0` above describes the repeat, not the")
        add("system.")
        add("")
        add("This is worth acting on rather than filing away. Whatever previously made this")
        add("gold set flip 6 of 15 items between runs is not reachable by repeating a")
        add("question — look at what differed instead: the route taken, the model, or the")
        add("state of the corpus. Varying *those* is what would measure stability here.")
        add("")
    elif latest.get("rounds", 1) > 1:
        add(f"Every item gave the same verdict in all {latest['rounds']} rounds, and the")
        add("answer text did vary between them — so the verdicts are genuinely stable.")
        add("")
    else:
        add("Single round — stability was not measured. Re-run with `--repeat 3`.")
        add("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=HISTORY_PATH)
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    entries = load_history(args.history)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(entries), encoding="utf-8")

    print(f"wrote {args.out} ({len(entries)} run(s) from {args.history})")


if __name__ == "__main__":
    main()
