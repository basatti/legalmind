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

        citations, renumbered = self._resolve_citations(cited, passages, reply)

        return Answer(
            text=renumbered,
            citations=citations,
            answered=True,
        )

    @staticmethod
    def _resolve_citations(
        numbers: list[int],
        passages: list[DocumentChunk],
        reply: str,
    ) -> tuple[tuple[Citation, ...], str]:
        """Translate passage numbers into places to check, and make the markers
        in the answer agree with the list that is shown beside it.

        Two numbering schemes meet here, and they are not the same one. The
        model is handed passages numbered 1..N and cites those numbers. What a
        reader is shown is the deduplicated list of *places* — several passages
        can come from one page, and one page can be cited repeatedly, so the
        list is shorter than N and numbered 1..k.

        Left alone, those disagree the moment the model does anything other than
        cite 1, 2, 3 in order. Observed live: a reply citing passages [1] and
        [3] rendered under a source list of [1] and [2] — a marker pointing at a
        source that was not there, next to a source nothing pointed at. For a
        product whose whole claim is a citation the reader can go and verify,
        that is not cosmetic.

        So the markers are rewritten to the reader's numbering. Every passage
        from the same page collapses onto the same new number, which is correct:
        they are the same place to check.

        Rewriting happens in one pass with a callback rather than repeated
        replacement, because replacing [3] with [2] and then [2] with something
        else would rewrite the text this function had just written.
        """
        renumber: dict[int, int] = {}
        unique: dict[tuple[int, int], int] = {}

        for number in numbers:
            passage = passages[number - 1]
            place = (passage.document_id, passage.page_number)

            if place not in unique:
                # First time this page is referred to: it takes the next number
                # in the list the reader sees.
                unique[place] = len(unique) + 1

            renumber[number] = unique[place]

        citations = tuple(
            Citation(document_id=document_id, page_number=page_number)
            for document_id, page_number in unique
        )

        def rewrite(match: re.Match[str]) -> str:
            # Only markers that passed the range check above are remapped;
            # anything else is left exactly as the model wrote it.
            return f"[{renumber[int(match.group(1))]}]"

        return citations, _CITATION_MARKER.sub(rewrite, reply)
