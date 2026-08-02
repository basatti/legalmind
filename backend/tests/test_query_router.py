"""Tests for the scoped query:ask endpoint (LEG-61 + the LEG-14 wiring).

The real embedding model and language model are replaced here: an offline
provider produces vectors of the right width without reading 2GB from disk, and
a stub language model returns a fixed reply. These tests are about who may
retrieve what, not about answer quality — and CI has neither the model weights
nor a running Ollama.
"""

import pytest

from embeddings.offline import OfflineEmbeddingProvider
from foundation.models import (
    EMBEDDING_DIMENSIONS,
    Assignment,
    Case,
    Document,
    DocumentChunk,
    Role,
)
from main import app
from routers.query_router import get_embedding_provider, get_llm_provider
from services.llm import LLMProvider
from tests.conftest import create_user_and_login

STUB_REPLY = "The deadline is thirty days [1]."


class StubLLM(LLMProvider):
    """Always answers, always cites passage 1 — so anything the retrieval layer
    hands over comes back as a real answer."""

    def generate(self, prompt: str) -> str:
        return STUB_REPLY


def embedding_provider() -> OfflineEmbeddingProvider:
    return OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS)


@pytest.fixture
def fake_providers(client):
    """Swap both models for cheap stand-ins, for the life of one test."""
    app.dependency_overrides[get_embedding_provider] = embedding_provider
    app.dependency_overrides[get_llm_provider] = StubLLM
    yield
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_llm_provider, None)


# --- fixtures for the data a question can be answered from -----------------


def make_case(session, title="Case") -> Case:
    case = Case(title=title, description=None, status="draft")
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def assign(session, user_id: int, case_id: int) -> None:
    session.add(Assignment(user_id=user_id, case_id=case_id))
    session.commit()


def make_searchable_chunk(session, case_id: int, uploaded_by: int) -> DocumentChunk:
    """One document with one chunk, so retrieval has something to find."""
    document = Document(
        case_id=case_id,
        filename="contract.pdf",
        file_path=f"storage/{case_id}/contract.pdf",
        uploaded_by=uploaded_by,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    text = "The notice period is thirty days from written notification."
    chunk = DocumentChunk(
        case_id=case_id,
        document_id=document.id,
        page_number=3,
        sequence=0,
        text=text,
        embedding=embedding_provider().embed([text])[0],
    )
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


def ask(client, question="What is the deadline?"):
    return client.post("/query/ask", json={"question": question})


# ---------------------------------------------------------------------------
# Permission guard
# ---------------------------------------------------------------------------


def test_unauthenticated_request_is_rejected(client):
    response = ask(client)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Assignment-scoped roles (Attorney/Paralegal)
# ---------------------------------------------------------------------------


def test_an_attorney_with_no_assigned_cases_gets_a_clean_no_answer(client, session):
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = ask(client)

    assert response.status_code == 200
    assert response.json()["answer"] is None


def test_an_attorney_assigned_to_the_case_gets_an_answer(client, session, fake_providers):
    case = make_case(session)
    user_id = create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, user_id, case.id)
    chunk = make_searchable_chunk(session, case.id, user_id)

    response = ask(client)
    body = response.json()

    print(body)
    assert response.status_code == 200
    assert body["answer"] == STUB_REPLY
    assert body["citations"] == [{"document_id": chunk.document_id, "page_number": 3}]


def test_an_attorney_gets_nothing_from_a_case_they_are_not_assigned_to(
    client, session, fake_providers
):
    """The epic's hard requirement: content exists and is findable, but not for
    this user — so the answer is empty rather than grounded in it."""
    theirs = make_case(session, "assigned")
    someone_elses = make_case(session, "not assigned")
    user_id = create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, user_id, theirs.id)
    make_searchable_chunk(session, someone_elses.id, user_id)

    response = ask(client)

    print(response.json())
    assert response.status_code == 200
    assert response.json()["answer"] is None


def test_a_paralegal_with_no_assigned_cases_gets_a_clean_no_answer(client, session):
    create_user_and_login(client, session, "priya@example.com", Role.PARALEGAL)

    response = ask(client)

    assert response.status_code == 200
    assert response.json()["answer"] is None


# ---------------------------------------------------------------------------
# Unscoped roles (Partner/Admin) -- case:read:any bypasses scoping entirely,
# even with zero rows in Assignment (LEG-61's core "reject only when
# genuinely empty" requirement).
# ---------------------------------------------------------------------------


def test_a_partner_with_zero_assignment_rows_still_retrieves(client, session, fake_providers):
    user_id = create_user_and_login(client, session, "pat@example.com", Role.PARTNER)
    case = make_case(session)
    make_searchable_chunk(session, case.id, user_id)

    response = ask(client)

    print(response.json())
    assert response.status_code == 200
    assert response.json()["answer"] == STUB_REPLY


def test_an_admin_with_zero_assignment_rows_still_retrieves(client, session, fake_providers):
    user_id = create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    case = make_case(session)
    make_searchable_chunk(session, case.id, user_id)

    response = ask(client)

    print(response.json())
    assert response.status_code == 200
    assert response.json()["answer"] == STUB_REPLY


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_an_empty_question_is_rejected(client, session):
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = client.post("/query/ask", json={"question": "   "})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Regression: FastAPI resolves every declared dependency of a route before
# running its handler, so building the real providers eagerly meant every
# request needed COMPANY_API_URL/COMPANY_API_KEY set - including requests
# rejected before ever reaching retrieval. get_embedding_provider and
# get_llm_provider must stay lazy (see LazyEmbeddingProvider/LazyLLMProvider),
# or these come back.
# ---------------------------------------------------------------------------


def test_a_rejected_request_never_needs_the_company_api_credentials(client, session, monkeypatch):
    monkeypatch.delenv("COMPANY_API_URL", raising=False)
    monkeypatch.delenv("COMPANY_API_KEY", raising=False)
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = client.post("/query/ask", json={"question": "   "})

    print(response.status_code, response.json())
    assert response.status_code == 422


def test_an_empty_authorized_scope_never_needs_the_company_api_credentials(
    client, session, monkeypatch
):
    monkeypatch.delenv("COMPANY_API_URL", raising=False)
    monkeypatch.delenv("COMPANY_API_KEY", raising=False)
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = ask(client)

    print(response.status_code, response.json())
    assert response.status_code == 200
    assert response.json()["answer"] is None
