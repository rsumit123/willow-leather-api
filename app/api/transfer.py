"""
Transfer Window API — Retention + Mini-Auction between seasons.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.career import (
    Career, Season, PlayerRetention, PlayerSeasonStats,
    CareerStatus, SeasonPhase, TeamSeasonStats,
)
from app.models.team import Team
from app.models.player import Player
from app.models.auction import Auction, AuctionStatus
from app.models.user import User
from app.auth.utils import get_current_user
from app.engine.transfer_engine import (
    get_retention_candidates,
    process_user_retentions,
    process_ai_retentions,
    release_and_generate_pool,
    prepare_next_season,
    create_mini_auction,
    _score_player,
    RETENTION_PRICES,
    MAX_RETENTIONS,
)
from app.engine.auction_engine import AuctionEngine
from app.api.schemas import (
    RetentionCandidateResponse,
    RetentionRequest,
    AIRetentionsResponse,
    TransferStatusResponse,
)

router = APIRouter(prefix="/transfer", tags=["Transfer"])


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _get_career_and_season(career_id: int, user: User, db: Session):
    """Helper to load and validate career + current season."""
    career = db.query(Career).filter_by(id=career_id, user_id=user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    season = db.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number,
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    return career, season


def _get_teams(career: Career, db: Session) -> list[Team]:
    """Get all teams (via first season's fixtures) for the career."""
    first_season = db.query(Season).filter_by(
        career_id=career.id, season_number=1
    ).first()
    if not first_season:
        raise HTTPException(status_code=404, detail="No season found")

    # Get unique team IDs from TeamSeasonStats
    team_ids = db.query(TeamSeasonStats.team_id).filter_by(
        season_id=first_season.id
    ).distinct().all()
    team_ids = [t[0] for t in team_ids]
    return db.query(Team).filter(Team.id.in_(team_ids)).all()


@router.post("/{career_id}/start")
def start_transfer_window(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transition career from POST_SEASON to TRANSFER_WINDOW."""
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.POST_SEASON:
        raise HTTPException(
            status_code=400,
            detail=f"Career must be in POST_SEASON status (currently: {career.status.value})"
        )

    career.status = CareerStatus.TRANSFER_WINDOW
    season.phase = SeasonPhase.TRANSFER_WINDOW
    db.commit()

    return {"status": "transfer_window", "message": "Transfer window opened"}


@router.get("/{career_id}/status")
def get_transfer_status(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current transfer window status."""
    career, season = _get_career_and_season(career_id, current_user, db)

    user_retentions = db.query(PlayerRetention).filter_by(
        season_id=season.id,
        team_id=career.user_team_id,
    ).count()

    teams = _get_teams(career, db)
    ai_team_ids = [t.id for t in teams if t.id != career.user_team_id]
    ai_retentions = db.query(PlayerRetention).filter(
        PlayerRetention.season_id == season.id,
        PlayerRetention.team_id.in_(ai_team_ids),
    ).count() if ai_team_ids else 0

    # Check if players have been released (any unassigned players exist that were previously on teams)
    unassigned_count = db.query(Player).filter(Player.team_id.is_(None)).count()

    # Check if mini-auction has started
    next_season = db.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number + 1,
    ).first()
    mini_auction_started = False
    if next_season:
        auction = db.query(Auction).filter_by(season_id=next_season.id).first()
        mini_auction_started = auction is not None

    return TransferStatusResponse(
        career_status=career.status.value,
        season_phase=season.phase.value,
        user_retentions_done=user_retentions > 0,
        ai_retentions_done=ai_retentions > 0,
        players_released=unassigned_count > 0,
        mini_auction_started=mini_auction_started,
    )


@router.get("/{career_id}/retention-candidates")
def get_retention_candidates_endpoint(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's squad with retention prices and season stats."""
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.TRANSFER_WINDOW:
        raise HTTPException(status_code=400, detail="Not in transfer window")

    user_team = db.query(Team).filter_by(id=career.user_team_id).first()
    if not user_team:
        raise HTTPException(status_code=404, detail="User team not found")

    # Return ALL squad players as retainable candidates, sorted by retention score
    all_players = db.query(Player).filter_by(team_id=user_team.id).all()

    # Score and sort all players
    scored = []
    for player in all_players:
        stats = db.query(PlayerSeasonStats).filter_by(
            season_id=season.id, player_id=player.id
        ).first()
        score = _score_player(player, stats)
        scored.append((player, score, stats))

    scored.sort(key=lambda x: x[1], reverse=True)

    result = []
    for i, (player, score, stats) in enumerate(scored):
        # Slot 1-4 get retention prices; all players are selectable
        slot = i + 1
        result.append(RetentionCandidateResponse(
            player_id=player.id,
            player_name=player.name,
            role=player.role.value if hasattr(player.role, 'value') else str(player.role),
            overall_rating=player.overall_rating,
            is_overseas=player.is_overseas,
            form=getattr(player, 'form', 1.0) or 1.0,
            age=player.age,
            season_runs=stats.runs if stats else 0,
            season_wickets=stats.wickets if stats else 0,
            retention_slot=slot,
            retention_price=RETENTION_PRICES.get(slot, 0),
        ))

    return result


@router.post("/{career_id}/retain")
def retain_players(
    career_id: int,
    request: RetentionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User submits their retention choices (up to 4 player IDs)."""
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.TRANSFER_WINDOW:
        raise HTTPException(status_code=400, detail="Not in transfer window")

    # Check if already retained
    existing = db.query(PlayerRetention).filter_by(
        season_id=season.id,
        team_id=career.user_team_id,
    ).count()
    if existing > 0:
        raise HTTPException(status_code=400, detail="Retentions already submitted")

    if len(request.player_ids) > MAX_RETENTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retain more than {MAX_RETENTIONS} players"
        )

    user_team = db.query(Team).filter_by(id=career.user_team_id).first()

    try:
        retentions = process_user_retentions(db, season, user_team, request.player_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    total_cost = sum(r.retention_price for r in retentions)
    return {
        "retained_count": len(retentions),
        "total_cost": total_cost,
        "remaining_budget": 900_000_000 - total_cost,
        "retained_players": [
            {
                "player_id": r.player_id,
                "retention_slot": r.retention_slot,
                "retention_price": r.retention_price,
            }
            for r in retentions
        ],
    }


@router.post("/{career_id}/process-ai-retentions")
def do_ai_retentions(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI teams decide their retentions. Returns summary."""
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.TRANSFER_WINDOW:
        raise HTTPException(status_code=400, detail="Not in transfer window")

    # Ensure user has already retained
    user_retentions = db.query(PlayerRetention).filter_by(
        season_id=season.id,
        team_id=career.user_team_id,
    ).count()
    if user_retentions == 0:
        raise HTTPException(
            status_code=400,
            detail="User must submit retentions first"
        )

    teams = _get_teams(career, db)

    # Check if AI retentions already done
    ai_team_ids = [t.id for t in teams if t.id != career.user_team_id]
    existing_ai = db.query(PlayerRetention).filter(
        PlayerRetention.season_id == season.id,
        PlayerRetention.team_id.in_(ai_team_ids),
    ).count() if ai_team_ids else 0

    if existing_ai > 0:
        raise HTTPException(status_code=400, detail="AI retentions already processed")

    results = process_ai_retentions(db, season, teams, career.user_team_id)
    db.commit()

    return AIRetentionsResponse(retentions=results)


@router.post("/{career_id}/release-and-prepare")
def release_and_prepare(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Release non-retained players and generate new auction pool."""
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.TRANSFER_WINDOW:
        raise HTTPException(status_code=400, detail="Not in transfer window")

    teams = _get_teams(career, db)

    pool_size = release_and_generate_pool(db, season, career, teams)
    db.commit()

    return {
        "players_in_pool": pool_size,
        "message": f"Released non-retained players. {pool_size} players available for mini-auction.",
    }


@router.post("/{career_id}/start-mini-auction")
def start_mini_auction(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create next season + mini-auction. Transitions career to AUCTION status.
    After this, the frontend uses the standard auction flow.
    """
    career, season = _get_career_and_season(career_id, current_user, db)

    if career.status != CareerStatus.TRANSFER_WINDOW:
        raise HTTPException(status_code=400, detail="Not in transfer window")

    teams = _get_teams(career, db)

    # Create next season and update career
    new_season = prepare_next_season(db, career, teams)

    # Create the auction
    auction = create_mini_auction(db, new_season, teams)

    # Initialize auction with AuctionEngine (categorize players, create entries)
    engine = AuctionEngine(db, auction)
    pool = db.query(Player).filter(Player.team_id.is_(None)).all()
    engine.initialize_auction(teams, pool)

    db.commit()

    return {
        "new_season_number": new_season.season_number,
        "auction_id": auction.id,
        "pool_size": auction.total_players,
        "career_status": career.status.value,
        "message": "Mini-auction created. Use the standard auction flow to proceed.",
    }
