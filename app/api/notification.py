"""
Notification API — Manager inbox system.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import Career, Notification
from app.models.user import User
from app.auth.utils import get_current_user
from app.api.schemas import NotificationResponse

router = APIRouter(prefix="/notification", tags=["Notification"])


def _get_career(career_id: int, user: User, db: Session) -> Career:
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    return career


@router.get("/{career_id}")
def get_notifications(
    career_id: int,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get notifications for a career, unread first."""
    career = _get_career(career_id, current_user, db)

    notifications = db.query(Notification).filter_by(
        career_id=career.id
    ).order_by(
        Notification.read,  # unread first (False < True)
        Notification.created_at.desc(),
    ).offset(offset).limit(limit).all()

    return [NotificationResponse.from_model(n) for n in notifications]


@router.get("/{career_id}/unread-count")
def get_unread_count(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get count of unread notifications."""
    career = _get_career(career_id, current_user, db)

    count = db.query(Notification).filter_by(
        career_id=career.id, read=False
    ).count()

    return {"unread_count": count}


@router.post("/{career_id}/{notification_id}/read")
def mark_read(
    career_id: int,
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    career = _get_career(career_id, current_user, db)

    notification = db.query(Notification).filter_by(
        id=notification_id, career_id=career.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read = True
    db.commit()
    return {"status": "read"}


@router.post("/{career_id}/read-all")
def mark_all_read(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all notifications as read."""
    career = _get_career(career_id, current_user, db)

    db.query(Notification).filter_by(
        career_id=career.id, read=False
    ).update({"read": True})
    db.commit()

    return {"status": "all_read"}
