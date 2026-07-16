from foundation.models import Assignment, Case, Role
from tests.conftest import create_user_and_login

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_case_directly(session, title="Test Case", status="draft"):
    case = Case(title=title, description=None, status=status)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def assign_user_to_case(session, user_id: int, case_id: int):
    assignment = Assignment(user_id=user_id, case_id=case_id)
    session.add(assignment)
    session.commit()


def upload_file(client, case_id: int, filename="test.pdf", content=b"fake pdf content"):
    return client.post(
        f"/cases/{case_id}/documents/",
        files={"file": (filename, content, "application/pdf")},
    )


# ---------------------------------------------------------------------------
# Upload — happy paths
# ---------------------------------------------------------------------------


def test_partner_can_upload_document_to_any_case(client, session):
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case = create_case_directly(session)

    response = upload_file(client, case.id)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "test.pdf"
    assert body["case_id"] == case.id


def test_assigned_attorney_can_upload_document(client, session):
    user_id = create_user_and_login(client, session, "attorney@example.com", Role.ATTORNEY)
    case = create_case_directly(session)
    assign_user_to_case(session, user_id, case.id)

    response = upload_file(client, case.id)

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Upload — authorization failures
# ---------------------------------------------------------------------------


def test_unassigned_attorney_cannot_upload_document(client, session):
    create_user_and_login(client, session, "attorney2@example.com", Role.ATTORNEY)
    case = create_case_directly(session)

    response = upload_file(client, case.id)

    assert response.status_code == 403


def test_unassigned_paralegal_cannot_upload_document(client, session):
    create_user_and_login(client, session, "paralegal@example.com", Role.PARALEGAL)
    case = create_case_directly(session)

    response = upload_file(client, case.id)

    assert response.status_code == 403


def test_upload_to_nonexistent_case_returns_404(client, session):
    create_user_and_login(client, session, "partner2@example.com", Role.PARTNER)

    response = upload_file(client, 99999)

    assert response.status_code == 404


def test_upload_requires_authentication(client):
    response = client.post(
        "/cases/1/documents/",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# List — happy paths
# ---------------------------------------------------------------------------


def test_partner_can_list_documents_for_any_case(client, session):
    create_user_and_login(client, session, "partner3@example.com", Role.PARTNER)
    case = create_case_directly(session)
    upload_file(client, case.id, filename="a.pdf")
    upload_file(client, case.id, filename="b.pdf")

    response = client.get(f"/cases/{case.id}/documents/")

    assert response.status_code == 200
    filenames = [d["filename"] for d in response.json()]
    assert "a.pdf" in filenames
    assert "b.pdf" in filenames


def test_assigned_paralegal_can_list_documents(client, session):
    user_id = create_user_and_login(client, session, "paralegal2@example.com", Role.PARALEGAL)
    case = create_case_directly(session)
    assign_user_to_case(session, user_id, case.id)

    response = client.get(f"/cases/{case.id}/documents/")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# List — authorization failures
# ---------------------------------------------------------------------------


def test_unassigned_attorney_cannot_list_documents(client, session):
    create_user_and_login(client, session, "attorney3@example.com", Role.ATTORNEY)
    case = create_case_directly(session)

    response = client.get(f"/cases/{case.id}/documents/")

    assert response.status_code == 403


def test_list_documents_on_nonexistent_case_returns_404(client, session):
    create_user_and_login(client, session, "partner4@example.com", Role.PARTNER)

    response = client.get("/cases/99999/documents/")

    assert response.status_code == 404


def test_list_documents_requires_authentication(client):
    response = client.get("/cases/1/documents/")
    assert response.status_code == 401
    # ---------------------------------------------------------------------------


# File validation
# ---------------------------------------------------------------------------


def test_upload_rejects_disallowed_file_extension(client, session):
    create_user_and_login(client, session, "partner5@example.com", Role.PARTNER)
    case = create_case_directly(session)

    response = upload_file(client, case.id, filename="malware.exe")

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_upload_rejects_file_exceeding_max_size(client, session):
    create_user_and_login(client, session, "partner6@example.com", Role.PARTNER)
    case = create_case_directly(session)

    oversized_content = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte

    response = upload_file(client, case.id, filename="big.pdf", content=oversized_content)

    assert response.status_code == 400
    assert "exceeds maximum" in response.json()["detail"]


def test_upload_accepts_file_at_max_size(client, session):
    create_user_and_login(client, session, "partner7@example.com", Role.PARTNER)
    case = create_case_directly(session)

    max_size_content = b"x" * (10 * 1024 * 1024)  # exactly 10 MB

    response = upload_file(client, case.id, filename="exact.pdf", content=max_size_content)

    assert response.status_code == 201
