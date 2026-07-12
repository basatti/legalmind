def _login(client) -> None:
    client.post(
        "/auth/register",
        json={
            "email": "case-tester@example.com",
            "full_name": "Case Tester",
            "password": "password123",
            "role": "admin",  # CRUD tests check case behavior, not authorization
        },
    )
    client.post(
        "/auth/login",
        json={"email": "case-tester@example.com", "password": "password123"},
    )


def test_create_case(client):
    _login(client)

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


def test_create_case_rejects_empty_title(client):
    _login(client)

    response = client.post("/cases/", json={"title": "   "})

    assert response.status_code == 422


def test_list_cases(client):
    _login(client)
    client.post("/cases/", json={"title": "Case A"})
    client.post("/cases/", json={"title": "Case B"})

    response = client.get("/cases/")

    assert response.status_code == 200
    titles = [case["title"] for case in response.json()]
    assert "Case A" in titles
    assert "Case B" in titles


def test_get_case(client):
    _login(client)
    created = client.post("/cases/", json={"title": "Findable Case"}).json()

    response = client.get(f"/cases/{created['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "Findable Case"


def test_get_case_not_found(client):
    _login(client)

    response = client.get("/cases/999999")

    assert response.status_code == 404


def test_update_case(client):
    _login(client)
    created = client.post("/cases/", json={"title": "Old Title", "description": "Old desc"}).json()

    response = client.patch(f"/cases/{created['id']}", json={"title": "New Title"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Title"
    assert body["description"] == "Old desc"  # untouched by partial update


def test_update_case_not_found(client):
    _login(client)

    response = client.patch("/cases/999999", json={"title": "Doesn't matter"})

    assert response.status_code == 404
