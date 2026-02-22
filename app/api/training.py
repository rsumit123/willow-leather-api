"""
Training API — Drill selection and stat boost management.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import (
    Career, GameDay, DayType, TrainingSession, DrillType,
)
from app.models.player import Player
from app.models.user import User
from app.auth.utils import get_current_user
from app.engine.tier_config import DRILL_CONFIG, TIER_CONFIG
from app.api.schemas import TrainRequest, DrillResponse, ActiveBoostResponse

router = APIRouter(prefix="/training", tags=["Training"])

TIER_ORDER = ["district", "state", "ipl"]


def _get_career(career_id: int, user: User, db: Session) -> Career:
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    return career


@router.get("/{career_id}/available-drills")
def get_available_drills(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get drills available for today's training session."""
    career = _get_career(career_id, current_user, db)

    # Check if today is a training day
    current_day = db.query(GameDay).filter_by(
        career_id=career.id, is_current=True
    ).first()

    if not current_day:
        raise HTTPException(status_code=400, detail="No calendar set up")

    if current_day.day_type != DayType.TRAINING:
        raise HTTPException(status_code=400, detail="Today is not a training day")

    # Check if already trained today
    existing = db.query(TrainingSession).filter_by(
        game_day_id=current_day.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already trained today")

    # Filter drills by tier
    tier = career.tier
    tier_idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0

    drills = []
    for drill_key, config in DRILL_CONFIG.items():
        min_tier_idx = TIER_ORDER.index(config["min_tier"])
        if tier_idx >= min_tier_idx:
            drills.append(DrillResponse(
                drill_type=drill_key,
                display_name=config["display_name"],
                description=config["description"],
                boost_attribute=config["boost_attribute"],
                boost_amount=config["boost_amount"],
                duration=config["duration"],
                best_for=config["best_for"],
                icon=config["icon"],
            ))

    return drills


@router.post("/{career_id}/train")
def run_training(
    career_id: int,
    request: TrainRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run a training session with selected drill and players."""
    career = _get_career(career_id, current_user, db)

    current_day = db.query(GameDay).filter_by(
        career_id=career.id, is_current=True
    ).first()

    if not current_day or current_day.day_type != DayType.TRAINING:
        raise HTTPException(status_code=400, detail="Today is not a training day")

    existing = db.query(TrainingSession).filter_by(
        game_day_id=current_day.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already trained today")

    if len(request.player_ids) > 5:
        raise HTTPException(status_code=400, detail="Max 5 players per session")

    if len(request.player_ids) == 0:
        raise HTTPException(status_code=400, detail="Select at least 1 player")

    # Validate drill type
    drill_key = request.drill_type
    if drill_key not in DRILL_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid drill type")

    config = DRILL_CONFIG[drill_key]

    # Validate players belong to user's team
    players = db.query(Player).filter(
        Player.id.in_(request.player_ids),
        Player.team_id == career.user_team_id,
    ).all()
    if len(players) != len(request.player_ids):
        raise HTTPException(status_code=400, detail="Some players not found in your team")

    # Create training session
    session = TrainingSession(
        career_id=career.id,
        season_id=current_day.season_id,
        game_day_id=current_day.id,
        drill_type=DrillType(drill_key),
        player_ids_json=json.dumps(request.player_ids),
        boost_attribute=config["boost_attribute"],
        boost_amount=config["boost_amount"],
        boost_expires_after_matches=config["duration"],
        matches_remaining=config["duration"],
    )
    db.add(session)
    db.commit()

    return {
        "status": "trained",
        "drill": config["display_name"],
        "players_trained": len(request.player_ids),
        "boost": f"+{config['boost_amount']} {config['boost_attribute']}",
        "duration": f"{config['duration']} matches",
    }


@router.get("/{career_id}/active-boosts")
def get_active_boosts(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all currently active training boosts."""
    career = _get_career(career_id, current_user, db)

    active = db.query(TrainingSession).filter(
        TrainingSession.career_id == career.id,
        TrainingSession.matches_remaining > 0,
    ).all()

    boosts = []
    for session in active:
        player_ids = json.loads(session.player_ids_json)
        for pid in player_ids:
            boosts.append(ActiveBoostResponse(
                player_id=pid,
                boost_attribute=session.boost_attribute,
                boost_amount=session.boost_amount,
                matches_remaining=session.matches_remaining,
                drill_type=session.drill_type.value,
            ))

    return boosts
