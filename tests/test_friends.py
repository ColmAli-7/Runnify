"""Friend requests: state changes need POST and the right user."""

from runnify.extensions import db
from runnify.models import FriendRequest, User
from runnify.security.passwords import hash_password
from tests.conftest import sign_in_as


def _make_user(app, email, name):
    with app.app_context():
        user = User(name=name, email=email, password_hash=hash_password("pw"))
        user.record_consent()
        db.session.add(user)
        db.session.commit()
        return user.id


def test_state_changing_friend_actions_reject_get(auth_client):
    assert auth_client.get("/friends/2/request").status_code == 405
    assert auth_client.get("/friends/requests/1/accept").status_code == 405
    assert auth_client.get("/friends/requests/1/decline").status_code == 405


def test_logout_requires_post(auth_client):
    assert auth_client.get("/logout").status_code == 405
    assert auth_client.post("/logout").status_code == 302
    assert auth_client.get("/dashboard").status_code == 302  # signed out


def test_request_accept_flow(app, auth_client, user):
    other = _make_user(app, "friend@example.com", "Friend")
    auth_client.post(f"/friends/{other}/request")
    with app.app_context():
        request_id = FriendRequest.query.one().id

    # only the receiver may accept: the sender cannot accept their own request
    auth_client.post(f"/friends/requests/{request_id}/accept")
    with app.app_context():
        assert db.session.get(FriendRequest, request_id).status == "pending"

    sign_in_as(auth_client, other)
    auth_client.post(f"/friends/requests/{request_id}/accept")
    with app.app_context():
        assert db.session.get(FriendRequest, request_id).status == "accepted"
        assert [f.id for f in db.session.get(User, user).friends] == [other]


def test_removing_a_friend_ends_it_both_ways(app, auth_client, user):
    other = _make_user(app, "friend@example.com", "Friend")
    with app.app_context():
        me, them = db.session.get(User, user), db.session.get(User, other)
        me.friends.append(them)
        them.friends.append(me)
        db.session.commit()
    assert auth_client.get("/friends/2/remove").status_code == 405
    auth_client.post(f"/friends/{other}/remove")
    with app.app_context():
        assert db.session.get(User, user).friends == []
        assert db.session.get(User, other).friends == []


def test_search_needs_two_characters_and_escapes_wildcards(app, auth_client, user):
    _make_user(app, "a@example.com", "Aoife Byrne")
    _make_user(app, "b@example.com", "100% Runner")
    assert b"Aoife" not in auth_client.get("/friends/search?q=A").data  # too short
    assert b"Aoife Byrne" in auth_client.get("/friends/search?q=oif").data
    assert b"100% Runner" in auth_client.get("/friends/search?q=0%25").data
    # "_" would match any letter if it weren't escaped ("Aoife" has an "fe")
    assert b"Aoife" not in auth_client.get("/friends/search?q=_e").data


def test_a_request_sent_from_search_returns_to_the_search(app, auth_client, user):
    other = _make_user(app, "friend@example.com", "Friend")
    response = auth_client.post(f"/friends/{other}/request", data={"next": "/friends/search?q=Fri"})
    assert response.headers["Location"] == "/friends/search?q=Fri"
    evil = auth_client.post(f"/friends/{other}/request", data={"next": "https://evil.example"})
    assert evil.headers["Location"] == "/friends"
