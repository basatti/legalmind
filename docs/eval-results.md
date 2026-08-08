# Evaluation results

**Generated — do not edit by hand.**
Regenerate with `uv run python scripts/eval_report.py` from `backend/`.

Source of truth is `backend/evals/history.jsonl`, one appended line per run of
`scripts/ragas_eval.py`. Per-item detail lives in `backend/evals/results/`, which
is gitignored — it is large and mostly Arabic answer text.

## How to read this

Every rate is the mean across the rounds of one run, `±` its standard deviation.
**A difference smaller than the spread is not a result.** A run with no `±` is a
single round: it measures that run, not the system, and cannot support a
comparison at all.

**A spread of `± 0.0` is not the same as a stable system.** The LLM provider pins
`temperature: 0`, so one prompt against one corpus produces one answer. Where a
run is marked *deterministic* below, every round returned byte-identical text —
the rounds re-ran the same computation, and agreeing with itself is the only
thing they could have done. Repeating is how you find that out; it is not, on
that evidence, a way to measure this pipeline's real variability.

**A RAGAS metric marked `(n/total graded)` does not describe the whole gold set.**
RAGAS returns NaN when a grade times out and those items drop silently out of the
mean. This has been observed hitting the Arabic items specifically, which is the
half that matters most here — a high faithfulness score covering only the English
items is not a result about this system.

"Cost" is tokens and latency. The company gateway is self-hosted, so there is no
vendor price to report and Langfuse's cost column is correctly $0.00 — see the
"A note on cost" section of `docs/observability.md`.

## Runs

| run | mode | commit | model | rounds | context hit | answer hit | answered | faithfulness | relevancy | unstable | mean ms | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260808-114513 | graph | 1f249be | gemma4 | 1 | 1.0 | 0.933 | 1.0 | — | — | not measured | 12430 | 25,326 |
| 20260808-112819 | graph | 1f249be | gemma4 | 1 | 1.0 | 0.933 | 1.0 | 0.963<br>*(10/15 graded)* | 0.749 | not measured | 12785 | 25,326 |
| 20260808-110719 | graph | 1f249be | gemma4 | 1 | 1.0 | 0.933 | 1.0 | — | — | not measured | 12846 | 25,326 |
| 20260808-084034 | graph | 1f249be | gemma4 | 1 | 1.0 | 0.933 | 1.0 | 0.917<br>*(8/15 graded)* | 0.75 | not measured | 12346 | 25,326 |
| 20260808-081733 | graph | 1f249be | gemma4 | 3 | 1.0 ± 0.0 | 0.933 ± 0.0 | 1.0 ± 0.0 | — | — | deterministic | 12371 | 75,978 |
| 20260808-081733 | direct | 1f249be | gemma4 | 3 | 1.0 ± 0.0 | 0.933 ± 0.0 | 1.0 ± 0.0 | — | — | deterministic | 12471 | 75,978 |
| 20260808-081043 | graph | 1f249be | gemma4 | 2 | 1.0 ± 0.0 | 0.933 ± 0.0 | 1.0 ± 0.0 | — | — | deterministic | 12357 | 50,652 |

## Latest run

`20260808-114513` — mode `graph`, commit `1f249be`, model `gemma4`, 1 round(s), top-k 5, multi-step `off`.

Single round — stability was not measured. Re-run with `--repeat 3`.
