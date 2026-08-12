"""Feedback carries the author's name, not just their id.

The thread rendered "User #29" and "User #30" — an id is what the UI keys on,
not something a lawyer can read. Same defect LEG-79 fixed for citations when
they showed "Document #2" instead of a filename, and the same fix.

Found by opening a real review thread in the browser, which is also the only
place it was ever visible: every endpoint returned the right data, and the
missing piece was data nobody had asked for.
"""

from foundation.hashing import hash_password
from foundation.models import Role, User

PARTNER = "perry@example.com"
PARTNER_NAME = "Perry Partner"
ATTORNEY = "attorney@example.com"
ATTORNEY_NAME = "Annie Attorney"

PASSWORD = "password123"


def make_user(session, email: str, name: str, role: Role) -> int:
    """Create a user with a distinct name.

    Distinct on purpose: `conftest.create_user_and_login` names everyone "Test
    User", which would let a test pass while attaching the *wrong* person's
    name to a comment. The whole point here is which name lands on which
    comment.
    """
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password(PASSWORD),
        role=role,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    return user.id


def login(client, email: str) -> None:
    """Sign in as an existing user, without creating one."""
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200


def open_case_for_review(client, session) -> int:
    """Drive a case to the point where a partner can open a review round."""
    attorney_id = make_user(session, ATTORNEY, ATTORNEY_NAME, Role.ATTORNEY)
    make_user(session, PARTNER, PARTNER_NAME, Role.PARTNER)

    login(client, PARTNER)
    case_id = client.post("/cases/", json={"title": "Review", "description": "d"}).json()["id"]
    client.post(f"/cases/{case_id}/assign", json={"user_id": attorney_id})
    client.post(f"/cases/{case_id}/transition", json={"target_status": "in_progress"})

    login(client, ATTORNEY)
    client.post(f"/cases/{case_id}/transition", json={"target_status": "submitted_for_review"})

    login(client, PARTNER)
    return case_id


def test_opening_a_review_returns_the_authors_name(client, session):
    case_id = open_case_for_review(client, session)

    body = client.post(f"/cases/{case_id}/reviews", json={"content": "Please revise."}).json()

    assert body["author_name"] == PARTNER_NAME
    # The id stays: it is what the UI compares on, and the name is for reading.
    assert isinstance(body["author_id"], int)


def test_a_reply_returns_its_own_authors_name(client, session):
    case_id = open_case_for_review(client, session)
    parent = client.post(f"/cases/{case_id}/reviews", json={"content": "Please revise."}).json()

    login(client, ATTORNEY)
    body = client.post(
        f"/cases/{case_id}/feedback",
        json={"content": "Revised.", "parent_id": parent["id"]},
    ).json()

    # The reply carries the attorney's name, not the partner's -- which is the
    # whole claim, and is why the two users have different names here.
    assert body["author_name"] == ATTORNEY_NAME
    assert body["author_id"] != parent["author_id"]


def test_the_whole_thread_carries_names(client, session):
    case_id = open_case_for_review(client, session)
    parent = client.post(f"/cases/{case_id}/reviews", json={"content": "Please revise."}).json()
    login(client, ATTORNEY)
    client.post(
        f"/cases/{case_id}/feedback", json={"content": "Revised.", "parent_id": parent["id"]}
    )

    login(client, PARTNER)
    thread = client.get(f"/cases/{case_id}/feedback").json()

    assert len(thread) == 2
    assert [item["author_name"] for item in thread] == [PARTNER_NAME, ATTORNEY_NAME]
    assert not any("User #" in item["author_name"] for item in thread)


def test_resolving_returns_the_name_too(client, session):
    """Every endpoint that returns a comment must carry it, or the thread
    changes shape depending on which call last touched it."""
    case_id = open_case_for_review(client, session)
    parent = client.post(f"/cases/{case_id}/reviews", json={"content": "Please revise."}).json()

    body = client.post(f"/cases/{case_id}/feedback/{parent['id']}/resolve").json()

    assert body["author_name"] == PARTNER_NAME
    assert body["resolved"] is True


def test_an_author_the_lookup_cannot_find_still_reads(client, session):
    """A comment whose author is missing must stay readable, not blank or 500.

    Tested against `_present` directly, because the database will not produce
    this state: `feedback.author_id` is a foreign key to `user.id` with no
    ON DELETE clause, so Postgres *rejects* deleting a user who has written
    anything. Verified against the live constraint rather than assumed.

    So this pins the defensive path, not a supported data state — the lookup
    returning nothing for an id. Worth keeping precisely because the FK is what
    holds today: the fallback is what stops a schema change from turning a gap
    into an exception in the middle of rendering a review.
    """
    from foundation.models import Feedback
    from routers.review_router import UNKNOWN_AUTHOR, _present

    orphan = Feedback(
        id=1,
        review_id=1,
        author_id=999999,
        content="Please revise.",
        parent_id=None,
        resolved=False,
    )

    presented = _present(orphan, {})

    assert presented.author_name == UNKNOWN_AUTHOR
    assert presented.content == "Please revise."
    assert presented.author_id == 999999


def test_one_query_serves_a_whole_thread(client, session):
    """The lookup is batched, so a long thread does not become N queries.

    Asserted through the repository rather than by counting SQL: `get_by_ids`
    is the seam, and it takes every author at once.
    """
    from repositories.user_repository import UserRepository

    case_id = open_case_for_review(client, session)
    client.post(f"/cases/{case_id}/reviews", json={"content": "Please revise."})
    thread = client.get(f"/cases/{case_id}/feedback").json()

    authors = UserRepository(session).get_by_ids(item["author_id"] for item in thread)

    assert set(authors) == {item["author_id"] for item in thread}


def test_looking_up_no_authors_asks_nothing(client, session):
    from repositories.user_repository import UserRepository

    assert UserRepository(session).get_by_ids([]) == {}
