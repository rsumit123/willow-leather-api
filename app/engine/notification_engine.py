"""
Notification Engine — Auto-generate notifications for game events.

Notifications are created by other engines (progression, match, training)
and this module provides helper functions for common patterns.
"""
from sqlalchemy.orm import Session
from app.models.career import Notification, NotificationType


def create_match_result_notification(
    db: Session, career_id: int, won: bool,
    opponent_name: str, margin: str, mom: str = None,
    fixture_id: int = None,
):
    """Create a notification for a match result."""
    if won:
        title = f"Won vs {opponent_name}"
        body = f"Victory by {margin}."
        icon = "trophy"
    else:
        title = f"Lost vs {opponent_name}"
        body = f"Defeated by {margin}."
        icon = "x-circle"

    if mom:
        body += f" Player of the Match: {mom}."

    action_url = f"/match/{fixture_id}" if fixture_id else None

    notif = Notification(
        career_id=career_id,
        type=NotificationType.MATCH_RESULT,
        title=title,
        body=body,
        icon=icon,
        action_url=action_url,
    )
    db.add(notif)
    return notif


def create_training_notification(
    db: Session, career_id: int, drill_name: str,
    players_count: int, boost_desc: str,
):
    """Create a notification for completed training."""
    notif = Notification(
        career_id=career_id,
        type=NotificationType.TRAINING,
        title=f"Training: {drill_name}",
        body=f"{players_count} player(s) trained. {boost_desc}.",
        icon="dumbbell",
    )
    db.add(notif)
    return notif


def create_milestone_notification(
    db: Session, career_id: int, title: str, body: str,
):
    """Create a milestone notification."""
    notif = Notification(
        career_id=career_id,
        type=NotificationType.MILESTONE,
        title=title,
        body=body,
        icon="star",
    )
    db.add(notif)
    return notif


def create_board_objective_notification(
    db: Session, career_id: int, description: str,
):
    """Notify user of a new board objective."""
    notif = Notification(
        career_id=career_id,
        type=NotificationType.BOARD_OBJECTIVE,
        title="Board Objective",
        body=description,
        icon="target",
    )
    db.add(notif)
    return notif
