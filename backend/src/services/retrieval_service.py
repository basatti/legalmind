"""Permission-aware retrieval (LEG-62).

One query: filter to the authorized cases, then rank top-k within that set —
never search-then-filter. See ChunkSearcher.search for the query itself.

This service does not decide what a user may see. The authorisation arrives as
an argument, already resolved by RagService, so there is exactly one place in
the system where scope is worked out.
"""

from dataclasses import dataclass

from embeddings import EmbeddingProvider, Vector
from foundation.authorization import AuthorizedCases, ChunkSearcher
from foundation.models import DocumentChunk

# Arabic and Latin sentence-ending punctuation. A chunk whose text doesn't
# end in one of these was very likely cut off mid-sentence by the chunker.
_SENTENCE_END = (".", "؟", "?", "!", "؛", ":")


@dataclass
class RetrievedMatch:
    """One retrieval hit plus any neighbouring chunks pulled in for context."""

    match: DocumentChunk
    context_chunks: list[DocumentChunk]  # match + neighbours, in sequence order


def unique_passages(matches: list[RetrievedMatch]) -> list[DocumentChunk]:
    """Flatten the matches into one ordered list, each chunk appearing once.

    Two matches close together in the same document can pull in the same
    neighbour, and a chunk sent twice would be numbered twice in the prompt
    — so the model could cite the same page under two different numbers.
    Keyed by (document, sequence) rather than by row id, since that holds
    whether or not the rows came from the database with ids populated.

    Lives here, beside `RetrievedMatch`, rather than on either caller: the
    graph's answer node and RagService both need it, and `services.rag_service`
    imports `graph.builder`, so a helper owned by the service and imported by
    the node would close an import cycle.
    """
    unique: dict[tuple[int, int], DocumentChunk] = {}
    for match in matches:
        for chunk in match.context_chunks:
            unique.setdefault((chunk.document_id, chunk.sequence), chunk)
    return list(unique.values())


class RetrievalService:
    def __init__(
        self,
        chunks: ChunkSearcher,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.chunks = chunks
        self.embedding_provider = embedding_provider

    def _looks_cut_off(self, chunk: DocumentChunk) -> bool:
        """True if this chunk's text doesn't stand on its own — i.e. it
        was very likely cut off at a chunk boundary."""
        text = chunk.text.strip()
        if not text:
            return False
        starts_clean = text[0].isupper() or not text[0].isalpha()
        ends_clean = text.endswith(_SENTENCE_END)
        return not (starts_clean and ends_clean)

    def _with_neighbours(self, chunk: DocumentChunk) -> list[DocumentChunk]:
        """The chunk plus its immediate sequence-neighbours in the same
        document, so a boundary cut doesn't lose the reader mid-sentence."""
        siblings = self.chunks.get_by_document(chunk.document_id)
        by_sequence = {c.sequence: c for c in siblings}

        wanted = [chunk.sequence - 1, chunk.sequence, chunk.sequence + 1]
        return [by_sequence[seq] for seq in wanted if seq in by_sequence]

    def retrieve(
        self,
        question: str,
        within: AuthorizedCases,
        top_k: int = 5,
    ) -> list[RetrievedMatch]:
        """Retrieve the passages for one question, inside `within` only.

        1. Embed the question.
        2. Rank the top-k chunks, scoped by the caller's authorisation.
        3. For any match that looks cut off, pull in its neighbours.
        """
        question_vector: Vector = self.embedding_provider.embed([question])[0]

        matches = self.chunks.search(
            query_vector=question_vector,
            within=within,
            limit=top_k,
        )

        results = []
        for match in matches:
            context = self._with_neighbours(match) if self._looks_cut_off(match) else [match]
            results.append(RetrievedMatch(match=match, context_chunks=context))
        return results
