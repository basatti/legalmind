"""Tests for the answer node (LEG-79).

What this file covers:

  * the passages handed to `AnswerService` are deduped, so a chunk pulled in
    by two overlapping matches is never numbered twice in one prompt;
  * the question answered is the original one, not the last sub-question a
    multi-step run happened to search for;
  * the node returns a partial update, like every other node.

What it does not cover: whether `AnswerService` writes a good answer, or
whether its citation validation is correct. Those are `test_answer_service.py`'s.
"""

from foundation.authorization import AllCases
from foundation.models import DocumentChunk
from graph.nodes import make_answer_node
from graph.state import GraphState
from services.answer_service import Answer, AnswerService
from services.retrieval_service import RetrievedMatch


class FakeAnswerService(AnswerService):
    """Records what it was asked to answer from. Deliberately does not call
    `super().__init__` — no LLM provider is involved, since these tests are
    about the node's contract with the service, not the service's own work.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[DocumentChunk]]] = []

    def answer(self, question: str, passages: list[DocumentChunk]) -> Answer:
        self.calls.append((question, passages))
        return Answer(text="stub answer [1]", citations=(), answered=True)


def chunk(document_id: int, sequence: int, text: str = "text") -> DocumentChunk:
    """An in-memory chunk. No embedding worth setting: nothing in the answer
    node looks at one."""
    return DocumentChunk(
        case_id=1,
        document_id=document_id,
        page_number=1,
        sequence=sequence,
        text=text,
        embedding=[],
    )


def match(*chunks: DocumentChunk) -> RetrievedMatch:
    return RetrievedMatch(match=chunks[0], context_chunks=list(chunks))


# --- passages are deduped -----------------------------------------------------


def test_a_chunk_pulled_in_by_two_matches_is_sent_once() -> None:
    """Two neighbouring hits in one document share a context chunk. Sending it
    twice would number the same page twice in the prompt, so the model could
    cite one page under two different numbers.
    """
    shared = chunk(document_id=1, sequence=5)
    node = make_answer_node(fake := FakeAnswerService())

    node(
        GraphState(
            question="q",
            authorized=AllCases(),
            matches=[
                match(chunk(1, 4), shared),
                match(shared, chunk(1, 6)),
            ],
        )
    )

    _, passages = fake.calls[0]
    keys = [(p.document_id, p.sequence) for p in passages]
    assert keys == [(1, 4), (1, 5), (1, 6)]


def test_same_sequence_in_different_documents_is_not_deduped() -> None:
    """Sequence numbers restart per document, so identity is the pair."""
    node = make_answer_node(fake := FakeAnswerService())

    node(
        GraphState(
            question="q",
            authorized=AllCases(),
            matches=[match(chunk(1, 0)), match(chunk(2, 0))],
        )
    )

    _, passages = fake.calls[0]
    assert [(p.document_id, p.sequence) for p in passages] == [(1, 0), (2, 0)]


def test_passages_keep_the_order_they_were_first_seen_in() -> None:
    """Passage numbers in the prompt come from this order, so it has to be
    stable rather than whatever a set would produce."""
    node = make_answer_node(fake := FakeAnswerService())

    node(
        GraphState(
            question="q",
            authorized=AllCases(),
            matches=[match(chunk(1, 9)), match(chunk(1, 2)), match(chunk(1, 9))],
        )
    )

    _, passages = fake.calls[0]
    assert [p.sequence for p in passages] == [9, 2]


# --- the question answered ----------------------------------------------------


def test_the_original_question_is_answered_not_the_last_sub_question() -> None:
    """`reasoning` drives retrieval, never the answer: the sub-questions were a
    way of finding passages, and the reply has to address what was asked.
    """
    node = make_answer_node(fake := FakeAnswerService())

    node(
        GraphState(
            question="the original compound question",
            authorized=AllCases(),
            reasoning=["a narrower sub-question"],
            matches=[match(chunk(1, 0))],
        )
    )

    assert fake.calls[0][0] == "the original compound question"


# --- the update is partial ----------------------------------------------------


def test_the_node_only_writes_answer() -> None:
    node = make_answer_node(FakeAnswerService())

    update = node(GraphState(question="q", authorized=AllCases(), matches=[match(chunk(1, 0))]))

    assert set(update.keys()) == {"answer"}
