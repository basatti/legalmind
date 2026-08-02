"""Permission-aware retrieval (LEG-62).

One query: filter to authorized case_ids, then rank top-k within that
set — never search-then-filter. See DocumentChunkRepository.search for
the query itself; this service resolves *which* case_ids a user is
authorized for, and stitches in neighbouring chunks when a match landed
at a chunk boundary.
"""

from dataclasses import dataclass

from embeddings import EmbeddingProvider, Vector
from foundation.models import DocumentChunk, User
from foundation.permissions import Permission, has_permission
from repositories.assignment_repository import AssignmentRepository
from repositories.document_chunk_repository import DocumentChunkRepository

# Arabic and Latin sentence-ending punctuation. A chunk whose text doesn't
# end in one of these was very likely cut off mid-sentence by the chunker.
_SENTENCE_END = (".", "؟", "?", "!", "؛", ":")


@dataclass
class RetrievedMatch:
    """One retrieval hit plus any neighbouring chunks pulled in for context."""

    match: DocumentChunk
    context_chunks: list[DocumentChunk]  # match + neighbours, in sequence order


class RetrievalService:
    def __init__(
        self,
        chunk_repository: DocumentChunkRepository,
        assignment_repository: AssignmentRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.chunk_repository = chunk_repository
        self.assignment_repository = assignment_repository
        self.embedding_provider = embedding_provider

    def _authorized_case_ids(self, user: User) -> list[int] | None:
        """None means unrestricted (case:read:any); otherwise the exact
        set of cases this user is assigned to."""
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return None
        assert user.id is not None
        return self.assignment_repository.get_case_ids_for_user(user.id)

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
        siblings = self.chunk_repository.get_by_document(chunk.document_id)
        by_sequence = {c.sequence: c for c in siblings}

        wanted = [chunk.sequence - 1, chunk.sequence, chunk.sequence + 1]
        return [by_sequence[seq] for seq in wanted if seq in by_sequence]

    def retrieve(self, user: User, question: str, top_k: int = 5) -> list[RetrievedMatch]:
        """Full permission-aware retrieval for one question.

        1. Resolve which cases this user may see.
        2. Embed the question and rank top-k chunks within that scope.
        3. For any match that looks cut off, pull in its neighbours.
        """
        authorized_case_ids = self._authorized_case_ids(user)

        question_vector: Vector = self.embedding_provider.embed([question])[0]
        matches = self.chunk_repository.search(
            question_vector=question_vector,
            authorized_case_ids=authorized_case_ids,
            top_k=top_k,
        )

        results = []
        for match in matches:
            context = self._with_neighbours(match) if self._looks_cut_off(match) else [match]
            results.append(RetrievedMatch(match=match, context_chunks=context))
        return results