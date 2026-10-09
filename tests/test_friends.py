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
