"""Tests for grounded answer generation (LEG-63).

Two things are being tested, and they are different in kind:

  * that the instruction sheet actually says what we claim it says — the ticket
    requires the template itself to be covered, not only the service;
  * that a reply which breaks the rules never reaches a lawyer.

What cannot be tested here is whether a real model obeys the instructions. No
test can establish that. What the tests can establish is that the instructions
were sent and that disobedience is caught.
"""

import pytest

from foundation.models import DocumentChunk
from services.answer_service import AnswerService, Citation
from services.llm import LLMProvider
from services.prompt import NOT_FOUND, build_prompt


def passage(
    text: str,
    document_id: int = 1,
    page_number: int = 1,
    sequence: int = 0,
) -> DocumentChunk:
    """A stored chunk, built in memory — none of these tests touch a database."""
    return DocumentChunk(
        document_id=document_id,
        case_id=1,
        sequence=sequence,
        page_number=page_number,
        text=text,
        embedding=[0.0],
    )


class FakeLLM(LLMProvider):
    """Replies with whatever the test decided, and remembers what it was asked."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


# --- the instruction sheet -------------------------------------------------


def test_passages_are_numbered_from_one() -> None:
    prompt = build_prompt("when does notice start?", ["first", "second"])
    print(prompt)
    assert "[1] first" in prompt
    assert "[2] second" in prompt


def test_the_question_is_included() -> None:
    prompt = build_prompt("when does notice start?", ["anything"])
    assert "when does notice start?" in prompt


def test_the_rules_forbid_answering_from_training() -> None:
    prompt = build_prompt("q", ["p"])
    assert "Never use knowledge from your training" in prompt


def test_the_rules_name_the_exact_not_found_token() -> None:
    prompt = build_prompt("q", ["p"])
    assert NOT_FOUND in prompt


def test_a_prompt_cannot_be_built_without_passages() -> None:
    with pytest.raises(ValueError):
        build_prompt("q", [])


# --- an answer that checks out ---------------------------------------------


def test_a_cited_answer_is_returned_with_its_source() -> None:
    model = FakeLLM("Notice begins the day after written notification [1].")
    service = AnswerService(model)

    answer = service.answer(
        "when does notice start?",
        [passage("...", document_id=7, page_number=4)],
    )

    print(f"answered={answer.answered} citations={answer.citations}")
    assert answer.answered
    assert answer.citations == (Citation(document_id=7, page_number=4),)


def test_each_source_is_listed_once_in_the_order_it_is_used() -> None:
    model = FakeLLM("First point [2]. Second point [1]. Third point [2].")
    service = AnswerService(model)

    answer = service.answer(
        "q",
        [
            passage("a", document_id=7, page_number=4, sequence=0),
            passage("b", document_id=9, page_number=1, sequence=1),
        ],
    )

    print(f"citations={answer.citations}")
    assert answer.citations == (
        Citation(document_id=9, page_number=1),
        Citation(document_id=7, page_number=4),
    )


# --- everything that must not reach a lawyer -------------------------------


def test_the_model_reporting_not_found_yields_no_answer() -> None:
    service = AnswerService(FakeLLM(NOT_FOUND))
    answer = service.answer("q", [passage("irrelevant text")])

    assert not answer.answered
    assert answer.citations == ()


def test_a_citation_of_a_passage_that_was_never_sent_is_discarded() -> None:
    """The clearest evidence a reply is not grounded: it points at something
    that does not exist."""
    service = AnswerService(FakeLLM("Confident and wrong [9]."))

    answer = service.answer("q", [passage("a"), passage("b")])

    print(f"answered={answer.answered} text={answer.text!r}")
    assert not answer.answered
    assert answer.text == ""


def test_an_answer_citing_nothing_at_all_is_discarded() -> None:
    service = AnswerService(FakeLLM("The notice period is thirty days."))

    answer = service.answer("q", [passage("a")])

    assert not answer.answered


def test_an_empty_reply_yields_no_answer() -> None:
    service = AnswerService(FakeLLM("   "))
    assert not service.answer("q", [passage("a")]).answered


# --- the case with nothing to read -----------------------------------------


def test_with_no_passages_the_model_is_never_asked() -> None:
    """A model handed a question and nothing to read answers from training."""
    model = FakeLLM("The notice period is thirty days.")
    service = AnswerService(model)

    answer = service.answer("q", [])

    print(f"prompts sent to the model: {len(model.prompts)}")
    assert not answer.answered
    assert model.prompts == []
