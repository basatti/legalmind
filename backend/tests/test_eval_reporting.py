"""Tests for the eval reporting rules (LEG-87).

`scripts/` is otherwise untested in this project, deliberately — the scripts
there are operational glue. These two are different: they decide *what a
number is allowed to claim*, and that judgement is the whole point of LEG-87.
A report that quietly presents one round as a measurement is worse than no
report, because it invites a conclusion the data cannot support.

So what is tested here is only the pure judgement logic — the spread rules,
flip detection, and how the document renders them. Nothing that talks to a
database, a gateway or Langfuse.
"""

import json
import sys
from pathlib import Path

import pytest

# The scripts are not an importable package: they are run as files, and add
# src/ to the path themselves. Adding their directory here is what lets the
# pure functions above be tested without turning scripts/ into a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import eval_report  # noqa: E402
from ragas_eval import ItemResult, answers_repeated_exactly, spread, unstable_items  # noqa: E402

from observability import build_tracer  # noqa: E402
from observability.tracer import NullTracer  # noqa: E402


def test_importing_the_harness_does_not_switch_tracing_on() -> None:
    """Importing `ragas_eval` loads backend/.env, credentials and all.

    Before conftest's `never_trace_from_tests` guard, that was enough to make
    every test in the suite trace for real: one run wrote 8 `rag-run` traces
    into the developer's live Langfuse, mixed in with the eval data LEG-87's
    report is built from. This test is the guard's alarm.
    """
    assert isinstance(build_tracer(), NullTracer)


def item(
    item_id: str, *, context_hit: bool, answer_hit: bool, answer_text: str = "an answer"
) -> ItemResult:
    """A result with only the fields the stability rules look at."""
    return ItemResult(
        id=item_id,
        lang="ar",
        question="?",
        expected_section="المادة",
        expected_answer_contains=["x"],
        answered=True,
        answer_text=answer_text,
        contexts=["a passage"],
        context_hit=context_hit,
        answer_hit=answer_hit,
        notes="",
    )


# --- spread ----------------------------------------------------------------


def test_one_round_reports_no_spread_rather_than_a_spread_of_zero() -> None:
    """The rule LEG-87 exists for.

    0.0 would say "this metric was stable". One round cannot say that — it was
    never measured twice. None is the only honest answer.
    """
    stats = spread([0.733])

    print(stats)
    assert stats["mean"] == 0.733
    assert stats["stdev"] is None
    assert stats["rounds"] == 1


def test_several_rounds_report_how_far_they_disagreed() -> None:
    stats = spread([0.6, 0.8, 0.7])

    print(stats)
    assert stats["mean"] == 0.7
    assert stats["stdev"] == 0.1
    assert (stats["min"], stats["max"]) == (0.6, 0.8)


def test_rounds_that_produced_no_number_are_not_counted_as_zero() -> None:
    """A skipped RAGAS grade is absent, not a score of nought.

    Averaging None in as 0.0 would drag faithfulness down every time a run
    used --skip-ragas, and the drop would look like a regression.
    """
    stats = spread([None, None])

    print(stats)
    assert stats["mean"] is None
    assert stats["rounds"] == 0


# --- flip detection --------------------------------------------------------


def test_an_item_that_changes_its_verdict_between_rounds_is_unstable() -> None:
    rounds = [
        [
            item("stable", context_hit=True, answer_hit=True),
            item("flips", context_hit=True, answer_hit=True),
        ],
        [
            item("stable", context_hit=True, answer_hit=True),
            item("flips", context_hit=True, answer_hit=False),
        ],
    ]

    assert unstable_items(rounds) == ["flips"]


def test_a_retrieval_flip_counts_even_when_the_answer_stays_right() -> None:
    """Both halves of the verdict matter.

    An item whose answer keeps matching while retrieval stops finding the
    article is getting the right answer for the wrong reason, and that is
    exactly the instability worth surfacing.
    """
    rounds = [
        [item("x", context_hit=True, answer_hit=True)],
        [item("x", context_hit=False, answer_hit=True)],
    ]

    assert unstable_items(rounds) == ["x"]


def test_a_single_round_reports_nothing_unstable_because_it_measured_nothing() -> None:
    """Not the same as "everything was stable" — see the report wording."""
    assert unstable_items([[item("x", context_hit=True, answer_hit=True)]]) == []


# --- determinism, which is why flip detection can be misread ----------------


def test_rounds_returning_identical_text_are_flagged_as_deterministic() -> None:
    """The observed case: temperature 0, same prompt, same bytes every round.

    Without this the run reports "0 unstable items", which reads as a stable
    system when it only means the rounds re-ran one computation.
    """
    rounds = [
        [item("x", context_hit=True, answer_hit=True, answer_text="واحد وعشرين يوماً")],
        [item("x", context_hit=True, answer_hit=True, answer_text="واحد وعشرين يوماً")],
    ]

    assert answers_repeated_exactly(rounds) is True


def test_one_differing_answer_is_enough_to_show_the_rounds_could_vary() -> None:
    rounds = [
        [
            item("same", context_hit=True, answer_hit=True, answer_text="identical"),
            item("differs", context_hit=True, answer_hit=True, answer_text="one phrasing"),
        ],
        [
            item("same", context_hit=True, answer_hit=True, answer_text="identical"),
            item("differs", context_hit=True, answer_hit=True, answer_text="another phrasing"),
        ],
    ]

    assert answers_repeated_exactly(rounds) is False


def test_a_single_round_cannot_say_whether_answers_repeat() -> None:
    """None, not False — nothing was compared."""
    assert answers_repeated_exactly([[item("x", context_hit=True, answer_hit=True)]]) is None


# --- reading the history ---------------------------------------------------


def test_a_half_written_line_does_not_destroy_the_history(tmp_path: Path) -> None:
    """The file is appended to by a long script that can be interrupted."""
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({"stamp": "20260808-090000", "mode": "graph"})
        + "\n{ interrupted mid-write\n"
        + json.dumps({"stamp": "20260808-100000", "mode": "direct"})
        + "\n",
        encoding="utf-8",
    )

    entries = eval_report.load_history(history)

    assert [e["stamp"] for e in entries] == ["20260808-090000", "20260808-100000"]


def test_a_missing_history_is_empty_rather_than_an_error(tmp_path: Path) -> None:
    assert eval_report.load_history(tmp_path / "nothing.jsonl") == []


# --- rendering -------------------------------------------------------------


def entry(**overrides) -> dict:
    base = {
        "stamp": "20260808-090000",
        "mode": "graph",
        "git_sha": "abc1234",
        "llm_model": "gemma4",
        "rounds": 3,
        "total": 15,
        "top_k": 5,
        "unstable_items": [],
        "mean_latency_ms": 4210,
        "total_tokens": {"total": 128000},
    }
    for key in eval_report.ALL_KEYS:
        base[key] = {"mean": 0.7, "stdev": 0.05, "min": 0.6, "max": 0.8, "rounds": 3}
    return {**base, **overrides}


def test_a_single_round_run_is_marked_as_not_measured() -> None:
    single = entry(rounds=1)
    for key in eval_report.ALL_KEYS:
        single[key] = {"mean": 0.7, "stdev": None, "min": 0.7, "max": 0.7, "rounds": 1}

    report = eval_report.render([single])

    print(report)
    assert "not measured" in report
    assert "Single round — stability was not measured" in report
    assert "±" not in report.split("## Runs")[1], "a single round must not render a spread"


def test_unstable_items_are_named_in_the_report() -> None:
    report = eval_report.render([entry(unstable_items=["sick-leave-full-pay-tier"])])

    assert "### Unstable items (1/15)" in report
    assert "`sick-leave-full-pay-tier`" in report


def test_a_clean_multi_round_run_says_so_explicitly() -> None:
    report = eval_report.render([entry(answers_repeated_exactly=False)])

    assert "Every item gave the same verdict in all 3 rounds" in report
    assert "answer text did vary between them" in report


def test_a_deterministic_run_is_never_presented_as_a_stable_system() -> None:
    """The correction that matters most in this file.

    Three rounds of byte-identical answers must not read as "0 unstable items,
    looks solid" — the rounds re-ran one computation.
    """
    report = eval_report.render([entry(answers_repeated_exactly=True)])

    print(report)
    assert "deterministic" in report
    assert "the rounds did not test anything" in report.lower()
    assert "0/15" not in report, "a deterministic run must not report a flip count"


def test_an_empty_history_still_renders_a_usable_document() -> None:
    report = eval_report.render([])

    assert "No runs recorded yet" in report


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        ({"mean": 0.7, "stdev": 0.05}, "0.7 ± 0.05"),
        ({"mean": 0.7, "stdev": None}, "0.7"),
        ({"mean": None, "stdev": None}, "—"),
        (None, "—"),
    ],
)
def test_a_metric_renders_its_spread_only_when_it_has_one(stats, expected: str) -> None:
    assert eval_report.cell({"context_hit_rate": stats}, "context_hit_rate") == expected


def test_a_ragas_mean_says_how_much_of_the_gold_set_it_covers() -> None:
    """The observed failure: 0.917 that described 8 items out of 15.

    RAGAS timed out on the other seven and returned NaN, and the seven it
    dropped were the Arabic ones — so the flattering number was the English
    subset wearing the whole set's name.
    """
    rendered = eval_report.cell(
        {
            "mean_faithfulness": {"mean": 0.917, "stdev": None},
            "faithfulness_graded": 8,
            "total": 15,
        },
        "mean_faithfulness",
    )

    assert "0.917" in rendered
    assert "(8/15 graded)" in rendered


def test_a_fully_graded_metric_is_not_cluttered_with_a_coverage_note() -> None:
    rendered = eval_report.cell(
        {
            "mean_answer_relevancy": {"mean": 0.75, "stdev": None},
            "answer_relevancy_graded": 15,
            "total": 15,
        },
        "mean_answer_relevancy",
    )

    assert rendered == "0.75"
