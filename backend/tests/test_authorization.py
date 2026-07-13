"""Authorization test suite (LEG-41).

Proves the permission matrix (LEG-39) and assignment scoping (LEG-40)
actually hold, for every role. Every test prints the real request outcome
before asserting on it — run with `-s` to see them.
"""

from foundation.models import Assignment, Case

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_and_login(client, email, role) -> int:
    """Register a user with a specific role, log them in, return their id."""
    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Test User",
            "password": "password123",
            "role": role,
        },
    )
    client.post("/auth/login", json={"email": email, "password": "password123"})
    return register_response.json()["id"]


def make_case(session, title="Case", status="draft") -> Case:
    case = Case(title=title, description=None, status=status)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def assign(session, user_id: int, case_id: int) -> None:
    """Directly insert an Assignment row — no API endpoint for this exists yet."""
    session.add(Assignment(user_id=user_id, case_id=case_id))
    session.commit()


# ---------------------------------------------------------------------------
# Attorney — assignment-scoped role (needs case:read/edit:assigned)
# ---------------------------------------------------------------------------


def test_attorney_cannot_read_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "amy@example.com", "attorney")

    response = client.get(f"/cases/{case.id}")
    print(f"\nUNASSIGNED Attorney tried to READ -> got {response.status_code}")

    assert response.status_code == 403


def test_attorney_cannot_edit_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "amy@example.com", "attorney")

    response = client.patch(f"/cases/{case.id}", json={"title": "Hacked"})
    print(f"\nUNASSIGNED Attorney tried to EDIT -> got {response.status_code}")

    assert response.status_code == 403


def test_attorney_can_read_assigned_case(client, session):
    case = make_case(session, title="Assigned Case")
    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case.id)

    response = client.get(f"/cases/{case.id}")
    print(f"\nASSIGNED Attorney tried to READ -> got {response.status_code}")

    assert response.status_code == 200


def test_attorney_can_edit_assigned_case(client, session):
    case = make_case(session, title="Assigned Case")
    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case.id)

    response = client.patch(f"/cases/{case.id}", json={"title": "Updated"})
    print(f"\nASSIGNED Attorney tried to EDIT -> got {response.status_code}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Paralegal — assignment-scoped role, same shape as Attorney
# ---------------------------------------------------------------------------


def test_paralegal_cannot_read_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "priya@example.com", "paralegal")

    response = client.get(f"/cases/{case.id}")
    print(f"\nUNASSIGNED Paralegal tried to READ -> got {response.status_code}")

    assert response.status_code == 403


def test_paralegal_cannot_edit_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "priya@example.com", "paralegal")

    response = client.patch(f"/cases/{case.id}", json={"title": "Hacked"})
    print(f"\nUNASSIGNED Paralegal tried to EDIT -> got {response.status_code}")

    assert response.status_code == 403


def test_paralegal_can_read_assigned_case(client, session):
    case = make_case(session, title="Assigned Case")
    user_id = register_and_login(client, "priya@example.com", "paralegal")
    assign(session, user_id, case.id)

    response = client.get(f"/cases/{case.id}")
    print(f"\nASSIGNED Paralegal tried to READ -> got {response.status_code}")

    assert response.status_code == 200


def test_paralegal_can_edit_assigned_case(client, session):
    case = make_case(session, title="Assigned Case")
    user_id = register_and_login(client, "priya@example.com", "paralegal")
    assign(session, user_id, case.id)

    response = client.patch(f"/cases/{case.id}", json={"title": "Updated"})
    print(f"\nASSIGNED Paralegal tried to EDIT -> got {response.status_code}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Partner — master-key role (case:read/edit:any, no assignment needed)
# ---------------------------------------------------------------------------


def test_partner_can_read_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "pete@example.com", "partner")

    response = client.get(f"/cases/{case.id}")
    print(f"\nUNASSIGNED Partner tried to READ -> got {response.status_code}")

    assert response.status_code == 200


def test_partner_can_edit_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "pete@example.com", "partner")

    response = client.patch(f"/cases/{case.id}", json={"title": "Updated"})
    print(f"\nUNASSIGNED Partner tried to EDIT -> got {response.status_code}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Admin — master-key role, same as Partner
# ---------------------------------------------------------------------------


def test_admin_can_read_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "alice@example.com", "admin")

    response = client.get(f"/cases/{case.id}")
    print(f"\nUNASSIGNED Admin tried to READ -> got {response.status_code}")

    assert response.status_code == 200


def test_admin_can_edit_unassigned_case(client, session):
    case = make_case(session, title="Unassigned Case")
    register_and_login(client, "alice@example.com", "admin")

    response = client.patch(f"/cases/{case.id}", json={"title": "Updated"})
    print(f"\nUNASSIGNED Admin tried to EDIT -> got {response.status_code}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# List scoping — GET /cases/ returns different sets per role
# ---------------------------------------------------------------------------


def test_attorney_list_only_shows_assigned_cases(client, session):
    case_a = make_case(session, title="Case A")
    make_case(session, title="Case B")
    make_case(session, title="Case C")

    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case_a.id)

    response = client.get("/cases/")
    titles = [c["title"] for c in response.json()]
    print(f"\nAmy (attorney, assigned to Case A only) sees: {titles}")

    assert titles == ["Case A"]


def test_paralegal_list_only_shows_assigned_cases(client, session):
    case_a = make_case(session, title="Case A")
    make_case(session, title="Case B")
    make_case(session, title="Case C")

    user_id = register_and_login(client, "priya@example.com", "paralegal")
    assign(session, user_id, case_a.id)

    response = client.get("/cases/")
    titles = [c["title"] for c in response.json()]
    print(f"\nPriya (paralegal, assigned to Case A only) sees: {titles}")

    assert titles == ["Case A"]


def test_partner_list_shows_all_cases(client, session):
    make_case(session, title="Case A")
    make_case(session, title="Case B")
    make_case(session, title="Case C")

    register_and_login(client, "pete@example.com", "partner")

    response = client.get("/cases/")
    titles = [c["title"] for c in response.json()]
    print(f"\nPete (partner, assigned to nothing) sees: {titles}")

    assert "Case A" in titles
    assert "Case B" in titles
    assert "Case C" in titles


# ---------------------------------------------------------------------------
# Create case — role-gated only (no assignment concept applies)
# ---------------------------------------------------------------------------


def test_paralegal_cannot_create_case(client, session):
    register_and_login(client, "priya@example.com", "paralegal")

    response = client.post("/cases/", json={"title": "New Case"})
    print(f"\nParalegal tried to CREATE a case -> got {response.status_code}")

    assert response.status_code == 403


def test_partner_can_create_case(client, session):
    register_and_login(client, "pete@example.com", "partner")

    response = client.post("/cases/", json={"title": "Partner's New Case"})
    print(f"\nPartner tried to CREATE a case -> got {response.status_code}")

    assert response.status_code == 201


def test_admin_can_create_case(client, session):
    register_and_login(client, "alice@example.com", "admin")

    response = client.post("/cases/", json={"title": "Admin's New Case"})
    print(f"\nAdmin tried to CREATE a case -> got {response.status_code}")

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Status transitions — role-gated AND assignment-gated together
# ---------------------------------------------------------------------------


def test_attorney_can_submit_assigned_case_for_review(client, session):
    case = make_case(session, title="Case", status="in_progress")
    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case.id)

    response = client.post(
        f"/cases/{case.id}/transition", json={"target_status": "submitted_for_review"}
    )
    print(f"\nASSIGNED Attorney tried to SUBMIT for review -> got {response.status_code}")

    assert response.status_code == 200


def test_attorney_cannot_submit_unassigned_case_for_review(client, session):
    case = make_case(session, title="Case", status="in_progress")
    register_and_login(client, "amy@example.com", "attorney")

    response = client.post(
        f"/cases/{case.id}/transition", json={"target_status": "submitted_for_review"}
    )
    print(f"\nUNASSIGNED Attorney tried to SUBMIT for review -> got {response.status_code}")

    assert response.status_code == 403


def test_partner_can_review_unassigned_case(client, session):
    case = make_case(session, title="Case", status="submitted_for_review")
    register_and_login(client, "pete@example.com", "partner")

    response = client.post(f"/cases/{case.id}/transition", json={"target_status": "under_review"})
    print(f"\nUNASSIGNED Partner tried to REVIEW -> got {response.status_code}")

    assert response.status_code == 200


def test_attorney_cannot_review_case(client, session):
    case = make_case(session, title="Case", status="submitted_for_review")
    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case.id)

    response = client.post(f"/cases/{case.id}/transition", json={"target_status": "under_review"})
    print(f"\nASSIGNED Attorney tried to REVIEW -> got {response.status_code}")

    assert response.status_code == 403


def test_attorney_cannot_close_case(client, session):
    case = make_case(session, title="Case", status="under_review")
    user_id = register_and_login(client, "amy@example.com", "attorney")
    assign(session, user_id, case.id)

    response = client.post(f"/cases/{case.id}/transition", json={"target_status": "closed"})
    print(f"\nASSIGNED Attorney tried to CLOSE -> got {response.status_code}")

    assert response.status_code == 403


def test_partner_can_close_unassigned_case(client, session):
    case = make_case(session, title="Case", status="under_review")
    register_and_login(client, "pete@example.com", "partner")

    response = client.post(f"/cases/{case.id}/transition", json={"target_status": "closed"})
    print(f"\nUNASSIGNED Partner tried to CLOSE -> got {response.status_code}")

    assert response.status_code == 200
