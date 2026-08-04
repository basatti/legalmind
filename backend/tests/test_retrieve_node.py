"""Tests for the retrieve node (LEG-77).

Three things are being tested:

  * the authorised scope reaches `RetrievalService.retrieve` unchanged — never
    recomputed, never widened, per LEG-66's invariant;
  * the query sent to retrieval is the question itself on a single-shot run,
    and the latest sub-question once `reason` has produced one;
  * matches accumulate rather than replace, since a multi-step run can call
    this node more than once.

What this file does not test: whether a real retrieval backend finds good
passages. That is `RetrievalService`'s own concern, not the node's.
"""

from foundation.authorization import AllCases, TheseCases
from graph import GraphState
from graph.nodes import make_retrieve_node
from services.retrieval_service import RetrievalService


class FakeRetrievalService(RetrievalService):
    """Returns a fixed, fake set of matches per call, and remembers what it
    was asked. Deliberately does not call `super().__init__` — no
    `ChunkSearcher` or `EmbeddingProvider` involved, since these tests are
    about the node's contract with the service, not the service's own
    behaviour.
    """

    def __init__(self, matches: list[str] | None = None) -> None:
        self.matches = matches if matches is not None else ["fake-match"]
        self.calls: list[tuple[str, object, int]] = []

    def retrieve(self, question: str, within, top_k: int = 5):
        self.calls.append((question, within, top_k))
        return self.matches


# --- the scope is passed through unchanged ----------------------------------


def test_the_authorized_scope_reaches_retrieval_unchanged() -> None:
    """The node must forward `state.authorized`, never recompute it."""
    scope = TheseCases(case_ids=frozenset({7}))
    node = make_retrieve_node(fake := FakeRetrievalService())

    node(GraphState(question="q", authorized=scope))

    assert fake.calls[0][1] is scope


def test_an_unrestricted_scope_is_forwarded_as_is() -> None:
    node = make_retrieve_node(fake := FakeRetrievalService())

    node(GraphState(question="q", authorized=AllCases()))

    assert fake.calls[0][1] == AllCases()


# --- choosing the query ------------------------------------------------------


def test_a_single_shot_question_is_retrieved_with_the_original_question() -> None:
    """No reasoning has run yet, so the question itself is the query."""
    node = make_retrieve_node(fake := FakeRetrievalService())

    node(GraphState(question="ما هي مدة فترة التجربة؟", authorized=AllCases()))

    assert fake.calls[0][0] == "ما هي مدة فترة التجربة؟"


def test_a_multi_step_question_is_retrieved_with_the_latest_sub_question() -> None:
    """Once `reason` has decomposed the question, retrieval works from that —
    not from the compound original still sitting in `state.question`.
    """
    node = make_retrieve_node(fake := FakeRetrievalService())
    state = GraphState(
        question="compound question nobody should search for as a whole",
        authorized=AllCases(),
        reasoning=["first sub-question", "second sub-question"],
    )

    node(state)

    assert fake.calls[0][0] == "second sub-question"


# --- matches accumulate -------------------------------------------------------


def test_matches_accumulate_rather_than_replace() -> None:
    """A second retrieval pass adds to what an earlier pass already found."""
    node = make_retrieve_node(FakeRetrievalService(matches=["new-match"]))
    state = GraphState(
        question="q",
        authorized=AllCases(),
        matches=["earlier-match"],
    )

    update = node(state)

    assert update["matches"] == ["earlier-match", "new-match"]


def test_a_first_pass_starts_from_no_matches() -> None:
    node = make_retrieve_node(FakeRetrievalService(matches=["only-match"]))

    update = node(GraphState(question="q", authorized=AllCases()))

    assert update["matches"] == ["only-match"]


# --- the update is partial ----------------------------------------------------


def test_the_node_only_writes_matches() -> None:
    """A node returns a partial update — only the field it changed."""
    node = make_retrieve_node(FakeRetrievalService())

    update = node(GraphState(question="q", authorized=AllCases()))

    assert set(update.keys()) == {"matches"}