"""Friends system: search, requests and the distance leaderboard."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from runnify.extensions import db, limiter
from runnify.models import FriendRequest, Run, User
from runnify.security.rate_limits import limit_from_config, user_or_ip

bp = Blueprint("friends", __name__)  # blueprint for friend system


@bp.route("/friends")
@login_required
def friends_page():
    """List friends with their total distance, plus pending incoming and outgoing requests."""
    friends = current_user.friends  # get all accepted friends
    friends_data = []
    for friend in friends:
        total_distance = (
            db.session.query(func.sum(Run.distance)).filter(Run.user_id == friend.id).scalar() or 0
        )
        total_distance_km = round(total_distance / 1000, 2)  # convert to km
        friends_data.append(
            {"id": friend.id, "name": friend.name, "total_distance": total_distance_km}
        )
    pending_requests = FriendRequest.query.filter_by(
        receiver_id=current_user.id, status="pending"
    ).all()  # incoming requests
    sent_requests = FriendRequest.query.filter_by(
        sender_id=current_user.id, status="pending"
    ).all()  # outgoing requests
    return render_template(
        "friends.html",
        friends=friends_data,
        pending_requests=pending_requests,
        sent_requests=sent_requests,
    )


@bp.route("/friends/send/<int:user_id>", methods=["POST"])
@login_required
def send_request(user_id):
    """Send a friend request to ``user_id`` unless already friends or one is pending."""
    if user_id == current_user.id:  # prevent adding self
        flash("You can't add yourself.", "error")
        return redirect(url_for("friends.friends_page"))
    user = db.get_or_404(User, user_id)
    if user in current_user.friends:  # already friends
        flash("You are already friends.", "info")
        return redirect(url_for("friends.friends_page"))
    existing = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user_id))
        | ((FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == current_user.id)),
        FriendRequest.status == "pending",
    ).first()  # check if a pending request exists
    if existing:
        flash("A request is already pending.", "info")
        return redirect(url_for("friends.friends_page"))
    new_request = FriendRequest(
        sender_id=current_user.id, receiver_id=user_id
    )  # create new request
    db.session.add(new_request)
    db.session.commit()
    flash("Friend request sent!", "success")
    return redirect(url_for("friends.friends_page"))


@bp.route("/friends/accept/<int:request_id>", methods=["POST"])
@login_required
def accept_request(request_id):
    """Accept a friend request addressed to the current user (adds the friendship both ways)."""
    fr = db.get_or_404(FriendRequest, request_id)
    if fr.receiver_id != current_user.id:  # only receiver can accept
        flash("Not authorised.", "error")
        return redirect(url_for("friends.friends_page"))
    fr.status = "accepted"
    fr.sender.friends.append(fr.receiver)  # add both directions
    fr.receiver.friends.append(fr.sender)
    db.session.commit()
    flash(f"You are now friends with {fr.sender.name}", "success")
    return redirect(url_for("friends.friends_page"))


@bp.route("/friends/decline/<int:request_id>", methods=["POST"])
@login_required
def decline_request(request_id):
    """Decline a friend request addressed to the current user."""
    fr = db.get_or_404(FriendRequest, request_id)
    if fr.receiver_id != current_user.id:  # prevent others from declining
        flash("Not authorised.", "error")
    else:
        fr.status = "declined"  # update status
        db.session.commit()
        flash("Friend request declined.", "info")
    return redirect(url_for("friends.friends_page"))


@bp.route("/friends/search", methods=["GET", "POST"])
@login_required
@limiter.limit(limit_from_config("SEARCH"), key_func=user_or_ip)
def search_users():
    """Search users by name (case-insensitive substring match on ``?q=``)."""
    query = request.args.get("q", "")  # search input
    results = []
    if query:
        results = User.query.filter(User.name.ilike(f"%{query}%")).all()  # case-insensitive search
    return render_template("friend_search.html", results=results, query=query)
