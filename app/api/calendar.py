"""
Calendar API — Day-by-day game progression.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import Career, Season, GameDay, DayType, Fixture
from app.models.user import User
from app.auth.utils import get_current_user
from app.api.schemas import (
    GameDayResponse,
    CalendarCurrentResponse,
    CalendarMonthResponse,
)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _get_career(career_id: int, user: User, db: Session) -> Career:
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    return career


def _enrich_game_day(day: GameDay, db: Session, user_team_id: int) -> GameDayResponse:
    """Convert GameDay model to response, enriching match days with fixture info."""
    fixture = None
    if day.fixture_id:
        fixture = db.query(Fixture).get(day.fixture_id)
    return GameDayResponse.from_model(day, fixture=fixture, user_team_id=user_team_id)


@router.get("/{career_id}/current")
def get_current_day(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current game day and upcoming 7 days."""
    career = _get_career(career_id, current_user, db)

    current_day = db.query(GameDay).filter_by(
        career_id=career.id, is_current=True
    ).first()

    if not current_day:
        return CalendarCurrentResponse(
            current_day=None,
            upcoming=[],
            has_calendar=False,
        )

    # Get next 7 days after current
    upcoming = db.query(GameDay).filter(
        GameDay.career_id == career.id,
        GameDay.date > current_day.date,
    ).order_by(GameDay.date).limit(7).all()

    user_team_id = career.user_team_id

    return CalendarCurrentResponse(
        current_day=_enrich_game_day(current_day, db, user_team_id),
        upcoming=[_enrich_game_day(d, db, user_team_id) for d in upcoming],
        has_calendar=True,
    )


@router.post("/{career_id}/advance")
def advance_day(
    career_id: int,
    skip_to_event: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Advance to the next day, or skip to the next match/training day."""
    career = _get_career(career_id, current_user, db)

    current_day = db.query(GameDay).filter_by(
        career_id=career.id, is_current=True
    ).first()

    if not current_day:
        raise HTTPException(status_code=400, detail="No calendar set up")

    if skip_to_event:
        # Skip to next match_day or training day
        next_day = db.query(GameDay).filter(
            GameDay.career_id == career.id,
            GameDay.date > current_day.date,
            GameDay.day_type.in_([DayType.MATCH_DAY, DayType.TRAINING]),
        ).order_by(GameDay.date).first()
    else:
        # Just advance one day
        next_day = db.query(GameDay).filter(
            GameDay.career_id == career.id,
            GameDay.date > current_day.date,
        ).order_by(GameDay.date).first()

    if not next_day:
        return {"message": "Season calendar complete", "season_ended": True}

    current_day.is_current = False
    next_day.is_current = True
    db.commit()

    return {
        "day": _enrich_game_day(next_day, db, career.user_team_id),
        "season_ended": False,
    }


@router.get("/{career_id}/month/{year}/{month}")
def get_month(
    career_id: int,
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all game days for a specific month."""
    career = _get_career(career_id, current_user, db)

    import calendar as cal

    _, last_day = cal.monthrange(year, month)
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-{last_day:02d}"

    days = db.query(GameDay).filter(
        GameDay.career_id == career.id,
        GameDay.date >= start,
        GameDay.date <= end,
    ).order_by(GameDay.date).all()

    user_team_id = career.user_team_id

    return CalendarMonthResponse(
        year=year,
        month=month,
        days=[_enrich_game_day(d, db, user_team_id) for d in days],
    )
