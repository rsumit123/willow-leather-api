"""
Calendar API — Day-by-day game progression.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import (
    Career, Season, GameDay, DayType, Fixture, FixtureStatus, FixtureType,
    TrainingPlan, Notification, NotificationType,
    SeasonPhase, CareerStatus,
)
from app.models.player import Player
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


def _get_ai_fixtures(db: Session, season_id: int, date_str: str, user_team_id: int) -> list:
    """Get AI vs AI fixtures scheduled on a given date."""
    fixtures = db.query(Fixture).filter(
        Fixture.season_id == season_id,
        Fixture.scheduled_date == date_str,
        Fixture.team1_id != user_team_id,
        Fixture.team2_id != user_team_id,
    ).all()

    result = []
    for f in fixtures:
        entry = {
            "id": f.id,
            "match_number": f.match_number,
            "team1_name": f.team1.short_name if f.team1 else "TBD",
            "team2_name": f.team2.short_name if f.team2 else "TBD",
            "status": f.status.value,
        }
        if f.status == FixtureStatus.COMPLETED and f.winner_id:
            if f.winner_id == f.team1_id:
                entry["winner_name"] = f.team1.short_name if f.team1 else "?"
            elif f.winner_id == f.team2_id:
                entry["winner_name"] = f.team2.short_name if f.team2 else "?"
            entry["result_summary"] = f.result_summary
        result.append(entry)

    return result


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

    # Get AI fixtures for today
    ai_fixtures_today = _get_ai_fixtures(
        db, current_day.season_id, current_day.date, user_team_id
    )

    response = CalendarCurrentResponse(
        current_day=_enrich_game_day(current_day, db, user_team_id),
        upcoming=[_enrich_game_day(d, db, user_team_id) for d in upcoming],
        has_calendar=True,
    )
    # Attach AI fixtures as extra field
    response_dict = response.model_dump()
    response_dict["ai_fixtures_today"] = ai_fixtures_today
    return response_dict


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
        next_day = db.query(GameDay).filter(
            GameDay.career_id == career.id,
            GameDay.date > current_day.date,
            GameDay.day_type.in_([DayType.MATCH_DAY, DayType.TRAINING]),
        ).order_by(GameDay.date).first()
    else:
        next_day = db.query(GameDay).filter(
            GameDay.career_id == career.id,
            GameDay.date > current_day.date,
        ).order_by(GameDay.date).first()

    if not next_day:
        # Auto-simulate remaining AI league fixtures before ending the season
        from app.engine.season_engine import SeasonEngine

        season = db.query(Season).filter_by(
            career_id=career.id,
            season_number=career.current_season_number,
        ).first()
        simulated = 0
        if season:
            engine = SeasonEngine(db, season)
            while True:
                fixture = engine.get_next_fixture()
                if not fixture or fixture.fixture_type != FixtureType.LEAGUE:
                    break
                try:
                    engine.simulate_match(fixture)
                    simulated += 1
                except ValueError:
                    break
            # Transition to playoffs if league is complete and playoffs not yet generated
            if engine.is_league_complete() and season.phase == SeasonPhase.LEAGUE_STAGE:
                # Check no playoff fixtures exist yet
                existing_playoffs = db.query(Fixture).filter(
                    Fixture.season_id == season.id,
                    Fixture.fixture_type != FixtureType.LEAGUE,
                ).count()
                if existing_playoffs == 0:
                    season.phase = SeasonPhase.PLAYOFFS
                    career.status = CareerStatus.PLAYOFFS
                    engine.generate_playoffs()
            db.commit()
        return {
            "message": "Season calendar complete",
            "season_ended": True,
            "remaining_simulated": simulated,
        }

    current_day.is_current = False
    next_day.is_current = True

    # ─── Auto-training on training days ─────────────────────────────
    training_results = None
    untrained_warning = None

    if next_day.day_type == DayType.TRAINING:
        from app.engine.training_engine_v2 import process_training_day

        results = process_training_day(db, career.id, next_day.id)

        if results:
            # Group by player
            trained_players = set(r["player_name"] for r in results)
            details = []
            for r in results:
                details.append(f"{r['player_name']}: {r['attribute']} +{r['gain']}")

            body = f"{len(trained_players)} player(s) trained.\n" + "\n".join(details[:10])
            if len(details) > 10:
                body += f"\n...and {len(details) - 10} more improvements"

            notif = Notification(
                career_id=career.id,
                type=NotificationType.TRAINING,
                title="Training Day Complete",
                body=body,
                icon="dumbbell",
                action_url="/training",
                metadata_json=json.dumps({"improvements": results[:20]}),
            )
            db.add(notif)
            training_results = results

        # Check for players without training plans
        team_players = db.query(Player).filter_by(team_id=career.user_team_id).all()
        plans = db.query(TrainingPlan).filter_by(career_id=career.id).all()
        plan_player_ids = {p.player_id for p in plans}
        untrained = [p for p in team_players if p.id not in plan_player_ids]

        if untrained:
            untrained_warning = {
                "count": len(untrained),
                "player_names": [p.name for p in untrained[:5]],
            }
            notif = Notification(
                career_id=career.id,
                type=NotificationType.TRAINING,
                title=f"{len(untrained)} player(s) have no training plan!",
                body="Set training plans for all players so they improve on training days.",
                icon="alert-triangle",
                action_url="/training",
            )
            db.add(notif)

    db.commit()

    # Get AI fixtures for the new day
    ai_fixtures = _get_ai_fixtures(
        db, next_day.season_id, next_day.date, career.user_team_id
    )

    return {
        "day": _enrich_game_day(next_day, db, career.user_team_id),
        "season_ended": False,
        "training_results": training_results,
        "untrained_warning": untrained_warning,
        "ai_fixtures_today": ai_fixtures,
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
