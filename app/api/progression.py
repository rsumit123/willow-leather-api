"""
Progression API — Career tier advancement, reputation, and manager stats.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.career import (
    Career, Season, BoardObjective, CareerStatus, SeasonPhase, TeamSeasonStats,
)
from app.models.user import User
from app.auth.utils import get_current_user
from app.engine.tier_config import TIER_CONFIG, get_reputation_title
from app.engine.progression_engine import evaluate_season_end, setup_next_season
from app.api.schemas import (
    ProgressionStatusResponse,
    ManagerStatsResponse,
    SeasonHistoryEntry,
    ObjectiveResponse,
)

router = APIRouter(prefix="/progression", tags=["Progression"])


def _get_career(career_id: int, user: User, db: Session) -> Career:
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    return career


@router.get("/{career_id}/status")
def get_progression_status(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current tier, reputation, and objectives."""
    career = _get_career(career_id, current_user, db)

    # Get current season objectives
    season = db.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number,
    ).first()

    objectives = []
    if season:
        objs = db.query(BoardObjective).filter_by(
            career_id=career.id, season_id=season.id
        ).all()
        objectives = [
            ObjectiveResponse(
                id=obj.id,
                description=obj.description,
                target_type=obj.target_type,
                target_value=obj.target_value,
                achieved=obj.achieved,
                consequence=obj.consequence,
            )
            for obj in objs
        ]

    tier_config = TIER_CONFIG.get(career.tier, TIER_CONFIG["ipl"])

    return ProgressionStatusResponse(
        tier=career.tier,
        reputation=career.reputation,
        reputation_title=get_reputation_title(career.reputation),
        trophies_won=career.trophies_won,
        seasons_played=career.seasons_played,
        current_season=career.current_season_number,
        game_over=career.game_over,
        game_over_reason=career.game_over_reason,
        promotion_condition=tier_config.get("promotion_condition"),
        objectives=objectives,
    )


@router.post("/{career_id}/accept-promotion")
def accept_promotion(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accept promotion to the next tier."""
    career = _get_career(career_id, current_user, db)

    if career.status != CareerStatus.POST_SEASON:
        raise HTTPException(status_code=400, detail="Not in post-season")

    tier_order = ["district", "state", "ipl"]
    current_idx = tier_order.index(career.tier) if career.tier in tier_order else 0

    if current_idx >= len(tier_order) - 1:
        raise HTTPException(status_code=400, detail="Already at highest tier")

    # Check if promotion is actually available
    season = db.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number,
    ).first()

    if not season or not season.champion_team_id:
        raise HTTPException(status_code=400, detail="Season not complete")

    tier_config = TIER_CONFIG.get(career.tier, {})
    promotion_condition = tier_config.get("promotion_condition")

    # Verify promotion condition met
    if promotion_condition == "win_trophy":
        if season.champion_team_id != career.user_team_id:
            raise HTTPException(status_code=400, detail="Must win trophy to be promoted")
    elif promotion_condition == "reach_final":
        if (season.champion_team_id != career.user_team_id and
                season.runner_up_team_id != career.user_team_id):
            raise HTTPException(status_code=400, detail="Must reach final to be promoted")

    next_tier = tier_order[current_idx + 1]
    career.tier = next_tier
    career.promoted_at_season = career.current_season_number

    # Set up the new tier — generate new teams, squads, fixtures, calendar
    _setup_promoted_career(db, career, next_tier)

    db.commit()

    return {
        "status": "promoted",
        "new_tier": next_tier,
        "message": f"Congratulations! You've been promoted to {next_tier.upper()} cricket!",
    }


@router.post("/{career_id}/evaluate-season")
def evaluate_season(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate a completed season — reputation, objectives, promotion/sacking."""
    career = _get_career(career_id, current_user, db)

    season = db.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number,
    ).first()

    if not season or season.phase != SeasonPhase.COMPLETED:
        raise HTTPException(status_code=400, detail="Season not yet complete")

    result = evaluate_season_end(db, career, season)
    return result


@router.post("/{career_id}/next-season")
def start_next_season(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start the next season at the same tier (no promotion)."""
    career = _get_career(career_id, current_user, db)

    if career.status != CareerStatus.POST_SEASON:
        raise HTTPException(status_code=400, detail="Not in post-season")

    if career.game_over:
        raise HTTPException(status_code=400, detail="Career is over")

    season = setup_next_season(db, career)

    return {
        "message": f"Season {season.season_number} has started!",
        "season_number": season.season_number,
        "tier": career.tier,
    }


def _setup_promoted_career(db: Session, career: Career, new_tier: str):
    """Set up a new career at the promoted tier with new teams and squads."""
    from app.models.team import Team
    from app.models.player import Player
    from app.models.playing_xi import PlayingXI
    from app.generators import TeamGenerator, PlayerGenerator
    from app.engine.season_engine import SeasonEngine
    from app.engine.calendar_engine import generate_season_calendar
    from app.api.career import _pick_best_xi, _pick_best_registered_squad, register_squad_for_team

    tier_config = TIER_CONFIG[new_tier]
    import random

    # Create new teams for the new tier
    teams = TeamGenerator.create_teams(
        career_id=career.id,
        user_team_index=random.randint(0, tier_config["team_count"] - 1),
        tier=new_tier,
    )
    for t in teams:
        db.add(t)
    db.flush()

    # Update user team
    user_team = next(t for t in teams if t.is_user_team)
    career.user_team_id = user_team.id

    # Generate squads
    max_rating = tier_config["max_player_rating"]
    squad_size = tier_config["squad_size"]
    all_indian = (tier_config["max_overseas"] == 0)

    for team in teams:
        players = PlayerGenerator.generate_team_squad(
            team_id=team.id,
            squad_size=squad_size,
            max_rating=max_rating,
            all_indian=all_indian,
        )
        for p in players:
            db.add(p)
    db.flush()

    # New season
    next_season_number = career.current_season_number + 1
    career.current_season_number = next_season_number
    career.status = CareerStatus.IN_SEASON

    season = Season(
        career_id=career.id,
        season_number=next_season_number,
        phase=SeasonPhase.LEAGUE_STAGE,
        total_league_matches=tier_config["total_league_matches"],
    )
    db.add(season)
    db.flush()

    # Auto-register squads and select XI
    playing_squad_size = tier_config.get("playing_squad")

    for team in teams:
        players = db.query(Player).filter_by(team_id=team.id).all()

        # If tier has a playing_squad concept (state: 15 from 25), auto-register best N
        if playing_squad_size and squad_size > playing_squad_size:
            registered = _pick_best_registered_squad(players, playing_squad_size)
            register_squad_for_team(
                db, career.id, season.id, team.id,
                [p.id for p in registered],
            )
            # Pick XI from the registered squad
            xi = _pick_best_xi(registered)
        else:
            # No registration needed (district) — pick XI from full squad
            xi = _pick_best_xi(players)

        for pos, player in enumerate(xi, 1):
            db.add(PlayingXI(
                team_id=team.id,
                season_id=season.id,
                player_id=player.id,
                position=pos,
            ))

    # Generate fixtures
    engine = SeasonEngine(db, season)
    engine.initialize_team_stats(teams)
    fixtures = engine.generate_league_fixtures(teams)

    # Generate calendar
    generate_season_calendar(db, career, season, fixtures)

    # Board objectives
    from app.engine.progression_engine import _create_tier_objectives
    _create_tier_objectives(db, career, season)


@router.get("/{career_id}/manager-stats")
def get_manager_stats(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get career-wide manager statistics."""
    career = _get_career(career_id, current_user, db)

    # Build season history
    seasons = db.query(Season).filter_by(
        career_id=career.id
    ).order_by(Season.season_number.desc()).all()

    from app.models.career import TeamSeasonStats

    history = []
    total_wins = 0
    total_matches = 0

    for season in seasons:
        stats = db.query(TeamSeasonStats).filter_by(
            season_id=season.id,
            team_id=career.user_team_id,
        ).first()

        wins = stats.wins if stats else 0
        losses = stats.losses if stats else 0
        played = stats.matches_played if stats else 0
        total_wins += wins
        total_matches += played

        # Determine finish position
        position = None
        if stats:
            all_stats = db.query(TeamSeasonStats).filter_by(
                season_id=season.id
            ).all()
            sorted_stats = sorted(all_stats, key=lambda s: (-s.points, -s.net_run_rate))
            for i, s in enumerate(sorted_stats):
                if s.team_id == career.user_team_id:
                    position = i + 1
                    break

        is_champion = season.champion_team_id == career.user_team_id
        is_runner_up = season.runner_up_team_id == career.user_team_id

        team_name = ""
        if career.user_team:
            team_name = career.user_team.name

        history.append(SeasonHistoryEntry(
            season_number=season.season_number,
            tier=career.tier,  # TODO: track tier per season
            team_name=team_name,
            wins=wins,
            losses=losses,
            position=position,
            is_champion=is_champion,
            is_runner_up=is_runner_up,
            is_current=season.season_number == career.current_season_number,
        ))

    win_percentage = round((total_wins / total_matches * 100), 1) if total_matches > 0 else 0

    return ManagerStatsResponse(
        manager_name=current_user.name or current_user.email,
        avatar_url=current_user.avatar_url,
        reputation=career.reputation,
        reputation_title=get_reputation_title(career.reputation),
        trophies_won=career.trophies_won,
        total_matches=total_matches,
        total_wins=total_wins,
        win_percentage=win_percentage,
        seasons_played=career.seasons_played,
        season_history=history,
    )
