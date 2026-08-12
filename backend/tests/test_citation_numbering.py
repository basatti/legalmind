"""The markers in an answer must match the source list shown beside it.

Found by asking a real question through the real UI, not by reading code. The
answer rendered as "…[1]… [3]" above a SOURCES list containing only [1] and
[2]: a marker pointing at a source that was not there, next to a source nothing
pointed at.

Two numbering schemes meet in `AnswerService`. The model is handed passages
numbered 1..N and cites those. The reader is shown the deduplicated list of
*places* — several passages can share a page — numbered 1..k. They agree only
when the model cites 1, 2, 3 in order, which is why every existing test missed
it: they all did.
"""

from foundation.models import DocumentChunk
from services.answer_service import AnswerService


class ScriptedProvider:
    """Returns one fixed reply, so the numbering is the only variable."""

    def __init__(self, reply: str):
        self.reply = reply

    def generate(self, prompt: str) -> str:
        return self.reply


def passage(document_id: int, page_number: int, text: str = "text") -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        page_number=page_number,
        chunk_index=0,
        text=text,
        embedding=None,
    )


def answer_for(reply: str, passages: list[DocumentChunk]):
    return AnswerService(ScriptedProvider(reply)).answer("q", passages)


def markers(text: str) -> list[int]:
    import re

    return [int(m) for m in re.findall(r"\[(\d+)\]", text)]


def test_a_gap_in_the_cited_passages_is_closed():
    """The live failure. Passages 1 and 3 of 3, from different pages: the
    reader sees two sources, so the markers must read [1] and [2]."""
    passages = [passage(1, 1), passage(1, 2), passage(2, 5)]

    result = answer_for("Claim one [1]. Claim two [3].", passages)

    assert markers(result.text) == [1, 2]
    assert len(result.citations) == 2


def test_every_marker_points_at_a_listed_source():
    """The invariant, stated directly: no marker may exceed the list length."""
    passages = [passage(1, 1), passage(1, 2), passage(2, 5), passage(3, 9)]

    result = answer_for("A [4]. B [2]. C [4].", passages)

    assert max(markers(result.text)) <= len(result.citations)
    assert min(markers(result.text)) >= 1


def test_passages_from_the_same_page_collapse_onto_one_number():
    """Two passages from one page are one place to check, so both markers must
    become the same number — not two entries for the same page."""
    passages = [passage(1, 7), passage(1, 7), passage(2, 3)]

    result = answer_for("First [1]. Second [2]. Third [3].", passages)

    assert markers(result.text) == [1, 1, 2]
    assert len(result.citations) == 2


def test_the_first_reference_decides_the_order():
    """Numbering follows the order the answer refers to places, not the order
    retrieval happened to return them."""
    passages = [passage(1, 1), passage(2, 2)]

    result = answer_for("Later passage first [2], then [1].", passages)

    assert markers(result.text) == [1, 2]
    assert result.citations[0].document_id == 2
    assert result.citations[1].document_id == 1


def test_a_reply_that_already_matches_is_unchanged():
    """The common case must not be disturbed — this is why the bug survived."""
    passages = [passage(1, 1), passage(2, 2)]

    result = answer_for("A [1]. B [2].", passages)

    assert result.text == "A [1]. B [2]."


def test_repeated_markers_stay_consistent():
    passages = [passage(1, 1), passage(2, 2), passage(3, 3)]

    result = answer_for("A [3]. B [1]. C [3].", passages)

    assert markers(result.text) == [1, 2, 1]
    assert len(result.citations) == 2


def test_renumbering_does_not_cascade():
    """Rewriting one marker must not then rewrite what it just wrote.

    [2]->[1] and [3]->[2] applied in sequence would turn the original [2] into
    [1] and then leave the new [2] to be rewritten again. One pass, not two.
    """
    passages = [passage(9, 9), passage(1, 1), passage(2, 2)]

    result = answer_for("A [2]. B [3].", passages)

    assert markers(result.text) == [1, 2]
    assert [c.document_id for c in result.citations] == [1, 2]


def test_an_out_of_range_marker_still_discards_the_whole_reply():
    """Renumbering must not become a way to launder a bad citation into a
    plausible one — the existing refusal comes first and still applies."""
    passages = [passage(1, 1)]

    result = answer_for("A [1]. B [7].", passages)

    assert result.answered is False
    assert result.text == ""
    assert result.citations == ()
