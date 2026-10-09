"""Friends: a monthly distance leaderboard, friend requests and finding people."""

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from runnify.extensions import db, limiter
from runnify.models import FriendRequest, Run, User, utcnow
from runnify.security.rate_limits import limit_from_config, user_or_ip
from runnify.security.redirects import safe_next_url

bp = Blueprint("friends", __name__)

MIN_SEARCH_LENGTH = 2
MAX_SEARCH_RESULTS = 20


def _leaderboard(people, since):
    """``(person, runs, metres)`` for ``people`` since ``since``, the furthest first."""
    totals = {
        user_id: (runs, metres)
        for user_id, runs, metres in db.session.query(
            Run.user_id, func.count(Run.id), func.coalesce(func.sum(Run.distance), 0)
        )
        .filter(Run.user_id.in_([person.id for person in people]), Run.date_time >= since)
        .group_by(Run.user_id)
    }
    board = [(person, *totals.get(person.id, (0, 0.0))) for person in people]
    return sorted(board, key=lambda entry: (-entry[2], entry[0].name.lower()))


@bp.route("/friends")
@login_required
def index():
    """The leaderboard for this month, plus requests waiting on either side."""
    now = utcnow()
    month_start = datetime(now.year, now.month, 1)
    return render_template(
        "friends/index.html",
        board=_leaderboard([current_user, *current_user.friends], month_start),
        month=now,
        incoming=FriendRequest.query.filter_by(receiver_id=current_user.id, status="pending").all(),
        outgoing=FriendRequest.query.filter_by(sender_id=current_user.id, status="pending").all(),
    )


@bp.route("/friends/<int:user_id>/request", methods=["POST"])
@login_required
def send_request(user_id):
    """Send a friend request to ``user_id`` unless already friends or one is pending."""
    back = redirect(safe_next_url(request.form.get("next")) or url_for("friends.index"))
    if user_id == current_user.id:
        flash("You can't add yourself.", "error")
        return back
    user = db.get_or_404(User, user_id)
    if user in current_user.friends:
        flash(f"You're already friends with {user.name}.", "info")
        return back
    existing = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user_id))
        | ((FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == current_user.id)),
        FriendRequest.status == "pending",
    ).first()
    if existing:
        flash("There's already a request waiting between you.", "info")
        return back
    db.session.add(FriendRequest(sender_id=current_user.id, receiver_id=user_id))
    db.session.commit()
    flash(f"Friend request sent to {user.name}.", "success")
    return back


@bp.route("/friends/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept(request_id):
    """Accept a friend request addressed to the current user (adds the friendship both ways)."""
    friend_request = db.get_or_404(FriendRequest, request_id)
    if friend_request.receiver_id != current_user.id or friend_request.status != "pending":
        flash("That request isn't yours to accept.", "error")
        return redirect(url_for("friends.index"))
    friend_request.status = "accepted"
    friend_request.sender.friends.append(friend_request.receiver)
    friend_request.receiver.friends.append(friend_request.sender)
    db.session.commit()
    flash(f"You're now friends with {friend_request.sender.name}.", "success")
    return redirect(url_for("friends.index"))


@bp.route("/friends/requests/<int:request_id>/decline", methods=["POST"])
@login_required
def decline(request_id):
    """Decline a friend request addressed to the current user."""
    friend_request = db.get_or_404(FriendRequest, request_id)
    if friend_request.receiver_id != current_user.id or friend_request.status != "pending":
        flash("That request isn't yours to decline.", "error")
    else:
        friend_request.status = "declined"
        db.session.commit()
        flash("Friend request declined.", "info")
    return redirect(url_for("friends.index"))


@bp.route("/friends/<int:user_id>/remove", methods=["POST"])
@login_required
def remove(user_id):
    """End a friendship, both ways."""
    friend = db.get_or_404(User, user_id)
    if friend in current_user.friends:
        current_user.friends.remove(friend)
    if current_user in friend.friends:
        friend.friends.remove(current_user)
    db.session.commit()
    flash(f"{friend.name} is no longer a friend.", "info")
    return redirect(url_for("friends.index"))


@bp.route("/friends/search")
@login_required
@limiter.limit(limit_from_config("SEARCH"), key_func=user_or_ip)
def search():
    """Find people by name (``?q=``, at least two characters, at most 20 results)."""
    query = request.args.get("q", "").strip()[:80]
    results = []
    if len(query) >= MIN_SEARCH_LENGTH:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        results = (
            User.query.filter(User.name.ilike(pattern, escape="\\"), User.id != current_user.id)
            .order_by(User.name)
            .limit(MAX_SEARCH_RESULTS)
            .all()
        )
    pending = {
        r.receiver_id
        for r in FriendRequest.query.filter_by(sender_id=current_user.id, status="pending")
    } | {
        r.sender_id
        for r in FriendRequest.query.filter_by(receiver_id=current_user.id, status="pending")
    }
    return render_template(
        "friends/search.html",
        query=query,
        results=results,
        friends={friend.id for friend in current_user.friends},
        pending=pending,
        min_length=MIN_SEARCH_LENGTH,
    )
