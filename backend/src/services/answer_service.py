"""Turns retrieved passages into a written answer (LEG-63).

Takes passages someone else has already found and authorised, so nothing here
touches the database, permissions or the logged-in user. What it adds is the
checking: a reply is only passed on once it has been shown to point at passages
that were actually provided.
"""

import logging
import re
from dataclasses import dataclass

from foundation.models import DocumentChunk
from services.llm import LLMProvider
from services.prompt import NOT_FOUND, build_prompt

logger = logging.getLogger(__name__)

_CITATION_MARKER = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Citation:
    """Where a claim came from, in terms a person can go and check."""

    document_id: int
    page_number: int


@dataclass(frozen=True)
class Answer:
    """A reply that has passed checking, or the absence of one.

    answered=False covers every way of having nothing to say: no passages were
    found, the model reported the answer was not in them, or its reply could not
    be trusted. The caller gets the same outcome in all three cases on purpose —
    a lawyer has no use for the distinction, and the difference is recorded in
    the logs, where it belongs.
    """

    text: str
    citations: tuple[Citation, ...]
    answered: bool

    @classmethod
    def none_found(cls) -> "Answer":
        return cls(text="", citations=(), answered=False)


class AnswerService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def answer(self, question: str, passages: list[DocumentChunk]) -> Answer:
        """Answer a question from these passages, or report that it cannot be."""
        if not passages:
            # Nothing to read. Asking anyway would leave the model only its
            # training to answer from, which is the outcome this ticket exists
            # to prevent.
            return Answer.none_found()

        prompt = build_prompt(question, [passage.text for passage in passages])
        reply = self.provider.generate(prompt).strip()

        if not reply or reply == NOT_FOUND:
            return Answer.none_found()

        cited = [int(marker) for marker in _CITATION_MARKER.findall(reply)]

        out_of_range = [number for number in cited if not 1 <= number <= len(passages)]
        if out_of_range:
            logger.warning(
                "reply cited passages %s but only %s were provided — discarded",
                out_of_range,
                len(passages),
            )
            return Answer.none_found()

        if not cited:
            logger.warning("reply cited no passage at all — discarded")
            return Answer.none_found()

        return Answer(
            text=reply,
            citations=self._citations(cited, passages),
            answered=True,
        )

    @staticmethod
    def _citations(numbers: list[int], passages: list[DocumentChunk]) -> tuple[Citation, ...]:
        """Translate passage numbers into documents and pages, in order, once each.

        Several passages can come from the same page, and a page can be cited
        repeatedly in one answer; the lawyer needs each place to check listed
        once, in the order the answer refers to them.
        """
        unique: dict[tuple[int, int], None] = {}
        for number in numbers:
            passage = passages[number - 1]
            unique[(passage.document_id, passage.page_number)] = None

        return tuple(
            Citation(document_id=document_id, page_number=page_number)
            for document_id, page_number in unique
        )
