"""Tests for permission-aware retrieval (LEG-62).

Two layers, tested separately:
  - DocumentChunkRepository.search: filter-then-rank, never search-then-filter.
  - RetrievalService: resolves *who* is authorized for *what*, and stitches
    in neighbouring chunks when a match landed at a chunk boundary.
"""

from embeddings import OfflineEmbeddingProvider
from foundation.models import Assignment, Case, Document, DocumentChunk, Role, User
from repositories.assignment_repository import AssignmentRepository
from repositories.document_chunk_repository import DocumentChunkRepository
from services.retrieval_service import RetrievalService

EMBEDDER = OfflineEmbeddingProvider(dimensions=1024)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_case(session, title="Case") -> Case:
    case = Case(title=title)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def make_user(session, email, role) -> User:
    from foundation.hashing import hash_password

    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password("password123"),
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_document(session, case: Case, uploader: User) -> Document:
    document = Document(
        case_id=case.id,
        filename="doc.pdf",
        file_path="/tmp/doc.pdf",
        uploaded_by=uploader.id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def make_chunk(session, case: Case, document: Document, text: str, sequence: int) -> DocumentChunk:
    """A chunk whose embedding exactly matches embed(text) -- so searching
    for `text` again lands this chunk at distance 0, the closest possible
    match. That gives tests a deterministic way to control ranking without
    depending on real semantic similarity."""
    chunk = DocumentChunk(
        case_id=case.id,
        document_id=document.id,
        page_number=1,
        sequence=sequence,
        text=text,
        embedding=EMBEDDER.embed([text])[0],
    )
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


def assign(session, user: User, case: Case) -> None:
    session.add(Assignment(user_id=user.id, case_id=case.id))
    session.commit()


# ---------------------------------------------------------------------------
# Repository: filter-then-rank
# ---------------------------------------------------------------------------


def test_search_never_returns_a_chunk_outside_the_authorized_cases(session):
    repo = DocumentChunkRepository(session)
    allowed_case = make_case(session, "Allowed")
    other_case = make_case(session, "Other")
    uploader = make_user(session, "u1@example.com", Role.ADMIN)

    allowed_doc = make_document(session, allowed_case, uploader)
    other_doc = make_document(session, other_case, uploader)

    make_chunk(session, allowed_case, allowed_doc, "termination clause", 0)
    other_match = make_chunk(session, other_case, other_doc, "termination clause", 0)

    # The other case's chunk is a perfect textual match for the query, but
    # it must never surface -- proves filtering happens before ranking,
    # not after.
    results = repo.search(
        question_vector=EMBEDDER.embed(["termination clause"])[0],
        authorized_case_ids=[allowed_case.id],
        top_k=5,
    )

    assert other_match.id not in [chunk.id for chunk in results]
    assert all(chunk.case_id == allowed_case.id for chunk in results)


def test_search_with_empty_authorized_list_returns_nothing(session):
    repo = DocumentChunkRepository(session)
    case = make_case(session)
    uploader = make_user(session, "u2@example.com", Role.ADMIN)
    document = make_document(session, case, uploader)
    make_chunk(session, case, document, "a clause", 0)

    results = repo.search(
        question_vector=EMBEDDER.embed(["a clause"])[0],
        authorized_case_ids=[],
        top_k=5,
    )

    assert results == []


def test_search_with_none_is_unrestricted(session):
    repo = DocumentChunkRepository(session)
    case_a = make_case(session, "A")
    case_b = make_case(session, "B")
    uploader = make_user(session, "u3@example.com", Role.ADMIN)
    doc_a = make_document(session, case_a, uploader)
    doc_b = make_document(session, case_b, uploader)
    make_chunk(session, case_a, doc_a, "clause one", 0)
    make_chunk(session, case_b, doc_b, "clause two", 0)

    results = repo.search(
        question_vector=EMBEDDER.embed(["clause one"])[0],
        authorized_case_ids=None,
        top_k=5,
    )

    assert {chunk.case_id for chunk in results} == {case_a.id, case_b.id}


def test_search_ranks_the_closest_match_first(session):
    repo = DocumentChunkRepository(session)
    case = make_case(session)
    uploader = make_user(session, "u4@example.com", Role.ADMIN)
    document = make_document(session, case, uploader)

    exact = make_chunk(session, case, document, "unfair dismissal", 0)
    unrelated = make_chunk(session, case, document, "parking regulations", 1)

    results = repo.search(
        question_vector=EMBEDDER.embed(["unfair dismissal"])[0],
        authorized_case_ids=[case.id],
        top_k=2,
    )

    assert results[0].id == exact.id
    assert results[-1].id == unrelated.id


def test_search_respects_top_k(session):
    repo = DocumentChunkRepository(session)
    case = make_case(session)
    uploader = make_user(session, "u5@example.com", Role.ADMIN)
    document = make_document(session, case, uploader)
    for i in range(5):
        make_chunk(session, case, document, f"clause {i}", i)

    results = repo.search(
        question_vector=EMBEDDER.embed(["clause 0"])[0],
        authorized_case_ids=[case.id],
        top_k=2,
    )

    assert len(results) == 2


# ---------------------------------------------------------------------------
# Service: authorization scoping
# ---------------------------------------------------------------------------


def _service(session) -> RetrievalService:
    return RetrievalService(
        chunk_repository=DocumentChunkRepository(session),
        assignment_repository=AssignmentRepository(session),
        embedding_provider=EMBEDDER,
    )


def test_attorney_only_retrieves_from_assigned_cases(session):
    assigned_case = make_case(session, "Assigned")
    other_case = make_case(session, "Not assigned")
    attorney = make_user(session, "attorney@example.com", Role.ATTORNEY)
    assign(session, attorney, assigned_case)

    assigned_doc = make_document(session, assigned_case, attorney)
    other_doc = make_document(session, other_case, attorney)
    make_chunk(session, assigned_case, assigned_doc, "شرط الإنهاء.", 0)
    make_chunk(session, other_case, other_doc, "شرط الإنهاء.", 0)

    results = _service(session).retrieve(attorney, "شرط الإنهاء.", top_k=5)

    assert all(r.match.case_id == assigned_case.id for r in results)


def test_partner_retrieves_across_all_cases(session):
    case_a = make_case(session, "A")
    case_b = make_case(session, "B")
    partner = make_user(session, "partner@example.com", Role.PARTNER)

    doc_a = make_document(session, case_a, partner)
    doc_b = make_document(session, case_b, partner)
    make_chunk(session, case_a, doc_a, "بند الإيجار.", 0)
    make_chunk(session, case_b, doc_b, "بند الإيجار.", 0)

    results = _service(session).retrieve(partner, "بند الإيجار.", top_k=5)

    assert {r.match.case_id for r in results} == {case_a.id, case_b.id}


def test_attorney_with_no_assignments_gets_nothing(session):
    case = make_case(session)
    attorney = make_user(session, "lonely@example.com", Role.ATTORNEY)
    admin = make_user(session, "admin_uploader@example.com", Role.ADMIN)
    document = make_document(session, case, admin)
    make_chunk(session, case, document, "بند الإيجار.", 0)

    results = _service(session).retrieve(attorney, "بند الإيجار.", top_k=5)

    assert results == []


# ---------------------------------------------------------------------------
# Service: boundary neighbours
# ---------------------------------------------------------------------------


def test_a_chunk_cut_off_mid_sentence_pulls_in_its_neighbours(session):
    case = make_case(session, "Boundary case")
    partner = make_user(session, "boundary_partner@example.com", Role.PARTNER)
    document = make_document(session, case, partner)

    before = make_chunk(session, case, document, "The tenant must give notice", 0)
    # No leading capital, no trailing punctuation -- looks cut off both ends.
    cut_off = make_chunk(session, case, document, "of at least thirty days before", 1)
    after = make_chunk(session, case, document, "vacating the premises.", 2)

    results = _service(session).retrieve(partner, "of at least thirty days before", top_k=1)

    assert len(results) == 1
    context_ids = {chunk.id for chunk in results[0].context_chunks}
    assert context_ids == {before.id, cut_off.id, after.id}


def test_a_clean_self_contained_chunk_does_not_pull_in_neighbours(session):
    case = make_case(session, "Clean case")
    partner = make_user(session, "clean_partner@example.com", Role.PARTNER)
    document = make_document(session, case, partner)

    make_chunk(session, case, document, "Unrelated preceding clause.", 0)
    clean = make_chunk(session, case, document, "The lease terminates on notice.", 1)
    make_chunk(session, case, document, "Unrelated following clause.", 2)

    results = _service(session).retrieve(partner, "The lease terminates on notice.", top_k=1)

    assert len(results) == 1
    assert [chunk.id for chunk in results[0].context_chunks] == [clean.id]