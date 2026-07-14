from foundation.models import Role
from tests.conftest import create_user_and_login


def _login(client, session) -> None:
    create_user_and_login(
        client, session, "case-tester@example.com", Role.ADMIN
    )  # CRUD tests check case behavior, not authorization


def test_create_case(client, session):
    _login(client, session)
    response = client.post(
        "/cases/",
        json={"title": "New Case", "description": "Some details"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "New Case"
    assert body["description"] == "Some details"
    assert body["status"] == "draft"
    assert "id" in body


def test_create_case_rejects_empty_title(client, session):
    _login(client, session)
    response = client.post("/cases/", json={"title": "   "})
    assert response.status_code == 422


def test_list_cases(client, session):
    _login(client, session)
    client.post("/cases/", json={"title": "Case A"})
    client.post("/cases/", json={"title": "Case B"})
    response = client.get("/cases/")
    assert response.status_code == 200
    titles = [case["title"] for case in response.json()]
    assert "Case A" in titles
    assert "Case B" in titles


def test_get_case(client, session):
    _login(client, session)
    created = client.post("/cases/", json={"title": "Findable Case"}).json()
    response = client.get(f"/cases/{created['id']}")
    assert response.status_code == 200
    assert response.json()["title"] == "Findable Case"


def test_get_case_not_found(client, session):
    _login(client, session)
    response = client.get("/cases/999999")
    assert response.status_code == 404


def test_update_case(client, session):
    _login(client, session)
    created = client.post("/cases/", json={"title": "Old Title", "description": "Old desc"}).json()
    response = client.patch(f"/cases/{created['id']}", json={"title": "New Title"})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Title"
    assert body["description"] == "Old desc"  # untouched by partial update


def test_update_case_not_found(client, session):
    _login(client, session)
    response = client.patch("/cases/999999", json={"title": "Doesn't matter"})
    assert response.status_code == 404
