"""
Training API — Persistent training plans + legacy drill/boost management.
"""
import json
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import (
    Career, GameDay, DayType, TrainingSession, DrillType,
    TrainingPlan, TrainingFocus, TrainingLog,
)
from app.models.player import Player
from app.models.user import User
from app.auth.utils import get_current_user
from app.engine.tier_config import DRILL_CONFIG, TIER_CONFIG
from app.engine.training_engine_v2 import (
    TRAINING_FOCUS_CONFIG, get_focus_options_for_player,
)
from app.api.schemas import (
    TrainRequest, DrillResponse, ActiveBoostResponse,
    SetTrainingPlanRequest, BulkTrainingPlanRequest,
    TrainingPlanPlayerResponse, FocusOptionResponse, TrainingPlansResponse,
    TrainingImprovementResponse,
)

router = APIRouter(prefix="/training", tags=["Training"])

TIER_ORDER = ["district", "state", "ipl"]


def _get_career(career_id: int, user: User, db: Session) -> Career:
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    return career


# ─── Training Plan Endpoints (v2) ──────────────────────────────────


@router.get("/{career_id}/plans")
def get_training_plans(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all training plans for user's team players, with DNA data."""
    career = _get_career(career_id, current_user, db)

    players = db.query(Player).filter_by(team_id=career.user_team_id).all()
    plans = db.query(TrainingPlan).filter_by(career_id=career.id).all()
    plan_map = {p.player_id: p for p in plans}

    player_list = []
    for player in players:
        plan = plan_map.get(player.id)
        batting_dna = player.batting_dna
        bowling_dna = player.bowler_dna
        valid_focuses = get_focus_options_for_player(player)

        player_list.append(TrainingPlanPlayerResponse(
            player_id=player.id,
            player_name=player.name,
            role=player.role.value,
            age=player.age,
            overall_rating=player.overall_rating,
            batting_skill=player.batting,
            bowling_skill=player.bowling,
            batting_dna=batting_dna.to_dict() if batting_dna else None,
            bowling_dna=bowling_dna.to_dict() if bowling_dna else None,
            bowling_type=player.bowling_type.value,
            current_focus=plan.focus.value if plan else None,
            focus_display_name=TRAINING_FOCUS_CONFIG[plan.focus.value]["display_name"] if plan else None,
            valid_focuses=valid_focuses,
        ))

    # Build focus options list
    focus_options = []
    for key, config in TRAINING_FOCUS_CONFIG.items():
        focus_options.append(FocusOptionResponse(
            focus=key,
            display_name=config["display_name"],
            description=config["description"],
            target_type=config["target_type"],
            target_attributes=config["target_attributes"],
            best_for_roles=config["best_for_roles"],
            icon=config["icon"],
        ))

    return TrainingPlansResponse(players=player_list, focus_options=focus_options)


@router.put("/{career_id}/plans/{player_id}")
def set_training_plan(
    career_id: int,
    player_id: int,
    request: SetTrainingPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or update a player's training focus."""
    career = _get_career(career_id, current_user, db)

    player = db.query(Player).filter_by(id=player_id, team_id=career.user_team_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found in your team")

    focus_key = request.focus
    if focus_key not in TRAINING_FOCUS_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid training focus")

    # Validate focus is valid for this player
    valid = get_focus_options_for_player(player)
    if focus_key not in valid:
        raise HTTPException(status_code=400, detail="This focus is not applicable to this player")

    # Upsert
    plan = db.query(TrainingPlan).filter_by(career_id=career.id, player_id=player_id).first()
    if plan:
        plan.focus = TrainingFocus(focus_key)
        plan.updated_at = datetime.utcnow()
    else:
        plan = TrainingPlan(
            career_id=career.id,
            player_id=player_id,
            focus=TrainingFocus(focus_key),
        )
        db.add(plan)

    db.commit()
    return {
        "status": "updated",
        "player_id": player_id,
        "focus": focus_key,
        "focus_display_name": TRAINING_FOCUS_CONFIG[focus_key]["display_name"],
    }


@router.delete("/{career_id}/plans/{player_id}")
def remove_training_plan(
    career_id: int,
    player_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a player's training plan."""
    career = _get_career(career_id, current_user, db)

    deleted = db.query(TrainingPlan).filter_by(
        career_id=career.id, player_id=player_id
    ).delete()

    db.commit()
    return {"status": "removed" if deleted else "not_found"}


@router.put("/{career_id}/plans/bulk")
def set_training_plans_bulk(
    career_id: int,
    request: BulkTrainingPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set training plans for multiple players at once."""
    career = _get_career(career_id, current_user, db)

    results = []
    for entry in request.plans:
        player = db.query(Player).filter_by(
            id=entry.player_id, team_id=career.user_team_id
        ).first()
        if not player:
            continue

        focus_key = entry.focus
        if focus_key not in TRAINING_FOCUS_CONFIG:
            continue

        valid = get_focus_options_for_player(player)
        if focus_key not in valid:
            continue

        plan = db.query(TrainingPlan).filter_by(
            career_id=career.id, player_id=entry.player_id
        ).first()
        if plan:
            plan.focus = TrainingFocus(focus_key)
            plan.updated_at = datetime.utcnow()
        else:
            plan = TrainingPlan(
                career_id=career.id,
                player_id=entry.player_id,
                focus=TrainingFocus(focus_key),
            )
            db.add(plan)

        results.append({"player_id": entry.player_id, "focus": focus_key})

    db.commit()
    return {"status": "updated", "updated_count": len(results), "plans": results}


@router.get("/{career_id}/focus-options")
def get_focus_options(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get available training focus options."""
    _get_career(career_id, current_user, db)

    options = []
    for key, config in TRAINING_FOCUS_CONFIG.items():
        options.append(FocusOptionResponse(
            focus=key,
            display_name=config["display_name"],
            description=config["description"],
            target_type=config["target_type"],
            target_attributes=config["target_attributes"],
            best_for_roles=config["best_for_roles"],
            icon=config["icon"],
        ))

    return options


@router.get("/{career_id}/history")
def get_training_history(
    career_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent training improvement history."""
    career = _get_career(career_id, current_user, db)

    logs = db.query(TrainingLog).filter_by(
        career_id=career.id
    ).order_by(TrainingLog.id.desc()).limit(limit).all()

    return [
        TrainingImprovementResponse(
            player_id=log.player_id,
            player_name=db.query(Player).get(log.player_id).name if db.query(Player).get(log.player_id) else "Unknown",
            focus=log.focus,
            attribute=log.attribute_improved,
            old_value=log.old_value,
            new_value=log.new_value,
            gain=log.improvement,
        )
        for log in logs
    ]


# ─── Legacy Endpoints (v1 drill-based) ─────────────────────────────


@router.get("/{career_id}/available-drills")
def get_available_drills(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get drills available for today's training session."""
    career = _get_career(career_id, current_user, db)

    current_day = db.query(GameDay).filter_by(
        career_id=career.id, is_current=True
    ).first()

    if not current_day:
        raise HTTPException(status_code=400, detail="No calendar set up")

    if current_day.day_type != DayType.TRAINING:
        raise HTTPException(status_code=400, detail="Today is not a training day")

    existing = db.query(TrainingSession).filter_by(
        game_day_id=current_day.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already trained today")

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
    """Run a training session with selected drill and players (legacy)."""
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

    drill_key = request.drill_type
    if drill_key not in DRILL_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid drill type")

    config = DRILL_CONFIG[drill_key]

    players = db.query(Player).filter(
        Player.id.in_(request.player_ids),
        Player.team_id == career.user_team_id,
    ).all()
    if len(players) != len(request.player_ids):
        raise HTTPException(status_code=400, detail="Some players not found in your team")

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
    """Get all currently active training boosts (legacy)."""
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
