"""
Career management API endpoints
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_session
from app.models.career import (
    Career, Season, CareerStatus, SeasonPhase,
    BoardObjective, GameDay, SquadRegistration,
)
from app.models.team import Team
from app.models.player import Player
from app.models.user import User
from app.models.auction import Auction, AuctionStatus
from app.models.playing_xi import PlayingXI
from app.generators import PlayerGenerator, TeamGenerator
from app.validators.playing_xi_validator import PlayingXIValidator
from app.auth.utils import get_current_user
from app.auth.config import settings
from app.engine.tier_config import TIER_CONFIG
from app.api.schemas import (
    CareerCreate, CareerResponse, CareerDetail, TeamChoice, TeamResponse,
    SquadResponse, PlayerResponse, PlayingXIRequest, PlayingXIPlayerResponse,
    PlayingXIResponse, PlayingXIValidationResponse,
    SquadRegistrationRequest, SquadRegistrationResponse,
)

router = APIRouter(prefix="/career", tags=["Career"])

MAX_CAREERS = settings.MAX_CAREERS_PER_USER


def parse_traits(traits_json: Optional[str]) -> List[str]:
    """Parse traits JSON string to list of trait strings"""
    if not traits_json:
        return []
    try:
        return json.loads(traits_json)
    except (json.JSONDecodeError, TypeError):
        return []


def _get_dna_dicts(player: Player) -> dict:
    """Get batting_dna and bowling_dna as dicts for PlayerResponse."""
    batting_dna = player.batting_dna
    bowling_dna = player.bowler_dna
    return {
        "batting_dna": batting_dna.to_dict() if batting_dna else None,
        "bowling_dna": bowling_dna.to_dict() if bowling_dna else None,
    }


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/teams/choices", response_model=List[TeamChoice])
def get_team_choices():
    """Get list of available teams to choose from"""
    return TeamGenerator.get_team_choices()


@router.post("/new", response_model=CareerDetail)
def create_career(
    career_data: CareerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new career.
    All careers start at District tier:
    - 6 teams with fixed 15-player squads (no auction)
    - Players capped at 65 OVR, all Indian
    - Calendar + board objectives auto-generated
    """
    # Check career limit
    existing_count = db.query(Career).filter_by(user_id=current_user.id).count()
    if existing_count >= MAX_CAREERS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_CAREERS} careers allowed. Delete one to create more."
        )

    tier = "district"
    tier_config = TIER_CONFIG[tier]

    # Create career at district tier — skip straight to IN_SEASON (no auction)
    career = Career(
        name=career_data.name,
        status=CareerStatus.IN_SEASON,
        tier=tier,
        reputation=0,
        user_id=current_user.id,
    )
    db.add(career)
    db.flush()

    # Create teams — district has 6 teams, user is auto-assigned
    teams = TeamGenerator.create_teams(
        career_id=career.id,
        user_team_index=career_data.team_index,  # None = random
        tier=tier,
    )
    for team in teams:
        db.add(team)
    db.flush()

    # Set user's team
    user_team = next(t for t in teams if t.is_user_team)
    career.user_team_id = user_team.id

    # Generate fixed squads for all teams (no auction pool)
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
        for player in players:
            db.add(player)
    db.flush()

    # Create first season
    season = Season(
        career_id=career.id,
        season_number=1,
        phase=SeasonPhase.LEAGUE_STAGE,
        total_league_matches=tier_config["total_league_matches"],
    )
    db.add(season)
    db.flush()

    # Auto-select playing XI for all teams (needs season.id)
    _auto_select_all_xi(teams, season.id, db)

    # Generate league fixtures
    from app.engine.season_engine import SeasonEngine
    engine = SeasonEngine(db, season)
    engine.initialize_team_stats(teams)
    fixtures = engine.generate_league_fixtures(teams)

    # Generate calendar from fixtures
    from app.engine.calendar_engine import generate_season_calendar
    generate_season_calendar(db, career, season, fixtures)

    # Create board objectives
    _create_district_objectives(db, career.id, season.id)

    db.commit()
    db.refresh(career)

    return CareerDetail(
        id=career.id,
        name=career.name,
        status=CareerStatus(career.status.value),
        current_season_number=career.current_season_number,
        user_team_id=career.user_team_id,
        tier=career.tier,
        reputation=career.reputation,
        trophies_won=career.trophies_won,
        game_over=career.game_over,
        created_at=career.created_at,
        user_team=TeamResponse.model_validate(user_team) if user_team else None,
    )


def _auto_select_all_xi(teams: list, season_id: int, db: Session):
    """Auto-select best playing XI for all teams (district: pick 11 from 15)."""
    from app.models.player import Player

    for team in teams:
        players = db.query(Player).filter_by(team_id=team.id).all()
        xi = _pick_best_xi(players)
        for pos, player in enumerate(xi, 1):
            db.add(PlayingXI(
                team_id=team.id,
                season_id=season_id,
                player_id=player.id,
                position=pos,
            ))
    db.flush()


def _pick_best_xi(players: list) -> list:
    """Pick the best 11 from a squad ensuring role balance."""
    from app.models.player import PlayerRole

    by_role = {}
    for p in players:
        role = p.role.value if hasattr(p.role, 'value') else p.role
        by_role.setdefault(role, []).append(p)

    # Sort each role by overall_rating descending
    for role in by_role:
        by_role[role].sort(key=lambda p: p.overall_rating, reverse=True)

    xi = []
    # Pick: 1 WK, 4 BAT, 3 BOWL, 2 AR, fill remaining from best available
    for role, count in [("wicket_keeper", 1), ("batsman", 4), ("bowler", 3), ("all_rounder", 2)]:
        available = by_role.get(role, [])
        xi.extend(available[:count])

    # Fill remaining from unused players
    used_ids = {p.id for p in xi}
    remaining = sorted(
        [p for p in players if p.id not in used_ids],
        key=lambda p: p.overall_rating, reverse=True
    )
    xi.extend(remaining[:11 - len(xi)])

    return xi[:11]


def _create_district_objectives(db: Session, career_id: int, season_id: int):
    """Create board objectives for a district season."""
    objectives = [
        BoardObjective(
            career_id=career_id,
            season_id=season_id,
            description="Win the District Cup",
            target_type="win_trophy",
            target_value=1,
            consequence="promotion",
        ),
        BoardObjective(
            career_id=career_id,
            season_id=season_id,
            description="Finish in Top 4",
            target_type="finish_position",
            target_value=4,
            consequence="stay",
        ),
    ]
    for obj in objectives:
        db.add(obj)


@router.get("/list", response_model=List[CareerResponse])
def list_careers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all saved careers for the current user"""
    careers = db.query(Career).filter_by(user_id=current_user.id).order_by(Career.updated_at.desc()).all()
    return [CareerResponse.model_validate(c) for c in careers]


@router.get("/{career_id}", response_model=CareerDetail)
def get_career(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get career details"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    user_team = db.query(Team).filter_by(id=career.user_team_id).first()

    return CareerDetail(
        id=career.id,
        name=career.name,
        status=CareerStatus(career.status.value),
        current_season_number=career.current_season_number,
        user_team_id=career.user_team_id,
        tier=career.tier,
        reputation=career.reputation,
        trophies_won=career.trophies_won,
        game_over=career.game_over,
        created_at=career.created_at,
        user_team=TeamResponse.model_validate(user_team) if user_team else None,
    )


@router.delete("/{career_id}")
def delete_career(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a career (and all associated data)"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # This would need cascade deletes set up properly
    # For now, just delete the career
    db.delete(career)
    db.commit()

    return {"message": "Career deleted"}


@router.get("/{career_id}/teams", response_model=List[TeamResponse])
def get_career_teams(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all teams in a career"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    teams = db.query(Team).filter_by(career_id=career_id).all()
    return [TeamResponse.model_validate(t) for t in teams]


@router.get("/{career_id}/teams/{team_id}/squad", response_model=SquadResponse)
def get_team_squad(
    career_id: int,
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a team's squad"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    team = db.query(Team).filter_by(id=team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    players = db.query(Player).filter_by(team_id=team_id).all()
    # Sort by overall_rating (property) in Python
    players = sorted(players, key=lambda p: p.overall_rating, reverse=True)

    player_responses = []
    for p in players:
        dna = _get_dna_dicts(p)
        player_responses.append(PlayerResponse(
            id=p.id,
            name=p.name,
            age=p.age,
            nationality=p.nationality,
            is_overseas=p.is_overseas,
            role=p.role.value,
            batting=p.batting,
            bowling=p.bowling,
            overall_rating=p.overall_rating,
            team_id=p.team_id,
            base_price=p.base_price,
            sold_price=p.sold_price,
            form=p.form,
            batting_style=p.batting_style.value,
            bowling_type=p.bowling_type.value,
            power=p.power,
            traits=parse_traits(p.traits),
            batting_intent=getattr(p, 'batting_intent', 'accumulator'),
            batting_dna=dna["batting_dna"],
            bowling_dna=dna["bowling_dna"],
        ))

    return SquadResponse(
        team=TeamResponse.model_validate(team),
        players=player_responses,
        total_players=len(players),
        overseas_count=sum(1 for p in players if p.is_overseas),
    )


@router.get("/{career_id}/playing-xi", response_model=PlayingXIResponse)
def get_playing_xi(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user team's playing XI"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # Get current season
    season = db.query(Season).filter_by(
        career_id=career_id,
        season_number=career.current_season_number
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    # Get playing XI entries for user's team
    xi_entries = db.query(PlayingXI).filter_by(
        team_id=career.user_team_id,
        season_id=season.id
    ).order_by(PlayingXI.position).all()

    players = []
    for entry in xi_entries:
        p = entry.player
        dna = _get_dna_dicts(p)
        players.append(PlayingXIPlayerResponse(
            id=p.id,
            name=p.name,
            age=p.age,
            nationality=p.nationality,
            is_overseas=p.is_overseas,
            role=p.role.value,
            batting=p.batting,
            bowling=p.bowling,
            overall_rating=p.overall_rating,
            team_id=p.team_id,
            base_price=p.base_price,
            sold_price=p.sold_price,
            form=p.form,
            batting_style=p.batting_style.value,
            bowling_type=p.bowling_type.value,
            power=p.power,
            traits=parse_traits(p.traits),
            batting_intent=getattr(p, 'batting_intent', 'accumulator'),
            position=entry.position,
            batting_dna=dna["batting_dna"],
            bowling_dna=dna["bowling_dna"],
        ))

    # Validate if we have players
    is_valid = False
    if players:
        player_objs = [entry.player for entry in xi_entries]
        validation = PlayingXIValidator.validate(player_objs)
        is_valid = validation["valid"]

    return PlayingXIResponse(
        players=players,
        is_valid=is_valid,
        is_set=len(players) == 11,
    )


@router.post("/{career_id}/playing-xi", response_model=PlayingXIResponse)
def set_playing_xi(
    career_id: int,
    request: PlayingXIRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set user team's playing XI (validates before saving)"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # Check career status allows XI changes (PRE_SEASON or IN_SEASON)
    if career.status not in [CareerStatus.PRE_SEASON, CareerStatus.IN_SEASON]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot set playing XI in {career.status.value} status"
        )

    # Get current season
    season = db.query(Season).filter_by(
        career_id=career_id,
        season_number=career.current_season_number
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    # Get the players
    players = db.query(Player).filter(
        Player.id.in_(request.player_ids),
        Player.team_id == career.user_team_id
    ).all()

    # Check all players belong to user's team
    if len(players) != len(request.player_ids):
        raise HTTPException(
            status_code=400,
            detail="Some players not found or don't belong to your team"
        )

    # If tier has squad registration (state), verify all XI players are in registered squad
    tier_config = TIER_CONFIG.get(career.tier, {})
    if tier_config.get("playing_squad"):
        registered = db.query(SquadRegistration).filter_by(
            career_id=career_id,
            season_id=season.id,
            team_id=career.user_team_id,
        ).all()
        registered_ids = {r.player_id for r in registered}
        if registered_ids:  # only enforce if registration exists
            invalid_ids = set(request.player_ids) - registered_ids
            if invalid_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"All playing XI must be from the registered squad. {len(invalid_ids)} player(s) not registered.",
                )

    # Validate the XI
    validation = PlayingXIValidator.validate(players)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail="; ".join(validation["errors"])
        )

    # Clear existing XI for this team/season
    db.query(PlayingXI).filter_by(
        team_id=career.user_team_id,
        season_id=season.id
    ).delete()

    # Save new XI with positions based on order in request
    for pos, player_id in enumerate(request.player_ids, 1):
        xi_entry = PlayingXI(
            team_id=career.user_team_id,
            season_id=season.id,
            player_id=player_id,
            position=pos
        )
        db.add(xi_entry)

    db.commit()

    # Return the saved XI
    xi_entries = db.query(PlayingXI).filter_by(
        team_id=career.user_team_id,
        season_id=season.id
    ).order_by(PlayingXI.position).all()

    player_responses = []
    for entry in xi_entries:
        p = entry.player
        dna = _get_dna_dicts(p)
        player_responses.append(PlayingXIPlayerResponse(
            id=p.id,
            name=p.name,
            age=p.age,
            nationality=p.nationality,
            is_overseas=p.is_overseas,
            role=p.role.value,
            batting=p.batting,
            bowling=p.bowling,
            overall_rating=p.overall_rating,
            team_id=p.team_id,
            base_price=p.base_price,
            sold_price=p.sold_price,
            form=p.form,
            batting_style=p.batting_style.value,
            bowling_type=p.bowling_type.value,
            power=p.power,
            traits=parse_traits(p.traits),
            batting_intent=getattr(p, 'batting_intent', 'accumulator'),
            position=entry.position,
            batting_dna=dna["batting_dna"],
            bowling_dna=dna["bowling_dna"],
        ))

    return PlayingXIResponse(
        players=player_responses,
        is_valid=True,
        is_set=True,
    )


@router.post("/{career_id}/playing-xi/validate", response_model=PlayingXIValidationResponse)
def validate_playing_xi(
    career_id: int,
    request: PlayingXIRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Validate proposed XI without saving (for real-time feedback)"""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # Get the players
    players = db.query(Player).filter(
        Player.id.in_(request.player_ids),
        Player.team_id == career.user_team_id
    ).all()

    # Validate the XI
    validation = PlayingXIValidator.validate(players)

    return PlayingXIValidationResponse(
        valid=validation["valid"],
        errors=validation["errors"],
        breakdown=validation["breakdown"]
    )


# ─── Squad Registration (State tier: pick 15 from 25) ───────────────


def _pick_best_registered_squad(players: list, squad_size: int) -> list:
    """Pick the best N players from a full squad ensuring role balance for registration."""
    from app.models.player import PlayerRole

    by_role = {}
    for p in players:
        role = p.role.value if hasattr(p.role, 'value') else p.role
        by_role.setdefault(role, []).append(p)

    # Sort each role by overall_rating descending
    for role in by_role:
        by_role[role].sort(key=lambda p: p.overall_rating, reverse=True)

    selected = []
    # Ensure minimum role coverage for a balanced registered squad:
    # 1 WK, 5 BAT, 4 BOWL, 3 AR = 13, then fill 2 more from best available
    for role, count in [("wicket_keeper", 1), ("batsman", 5), ("bowler", 4), ("all_rounder", 3)]:
        available = by_role.get(role, [])
        selected.extend(available[:count])

    # Fill remaining slots from unused players by rating
    used_ids = {p.id for p in selected}
    remaining = sorted(
        [p for p in players if p.id not in used_ids],
        key=lambda p: p.overall_rating, reverse=True
    )
    selected.extend(remaining[:squad_size - len(selected)])

    return selected[:squad_size]


def register_squad_for_team(
    db: Session,
    career_id: int,
    season_id: int,
    team_id: int,
    player_ids: list[int],
):
    """Save squad registration rows. Clears previous registration for same team/season."""
    # Clear existing
    db.query(SquadRegistration).filter_by(
        career_id=career_id,
        season_id=season_id,
        team_id=team_id,
    ).delete()

    for pid in player_ids:
        db.add(SquadRegistration(
            career_id=career_id,
            season_id=season_id,
            team_id=team_id,
            player_id=pid,
        ))
    db.flush()


@router.get("/{career_id}/squad-registration", response_model=SquadRegistrationResponse)
def get_squad_registration(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get registered squad for the user's team in the current season."""
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    tier_config = TIER_CONFIG.get(career.tier, {})
    playing_squad = tier_config.get("playing_squad", tier_config.get("squad_size", 15))

    # Get current season
    season = db.query(Season).filter_by(
        career_id=career_id,
        season_number=career.current_season_number,
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    registrations = db.query(SquadRegistration).filter_by(
        career_id=career_id,
        season_id=season.id,
        team_id=career.user_team_id,
    ).all()

    registered_ids = [r.player_id for r in registrations]

    return SquadRegistrationResponse(
        registered_player_ids=registered_ids,
        registered_count=len(registered_ids),
        max_allowed=playing_squad,
        is_complete=len(registered_ids) == playing_squad,
        tier=career.tier,
    )


@router.post("/{career_id}/squad-registration", response_model=SquadRegistrationResponse)
def set_squad_registration(
    career_id: int,
    request: SquadRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Set the registered playing squad for the user's team.
    At state tier: must register exactly 15 from 25.
    Validates player ownership, count, keeper presence, and overseas limits.
    Also auto-selects the best playing XI from the registered players.
    """
    career = db.query(Career).filter_by(id=career_id, user_id=current_user.id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    tier = career.tier
    tier_config = TIER_CONFIG.get(tier, {})
    playing_squad = tier_config.get("playing_squad")

    # For tiers without a playing_squad concept (district), skip validation
    if not playing_squad:
        raise HTTPException(
            status_code=400,
            detail=f"Squad registration is not required for {tier} tier",
        )

    # Get current season
    season = db.query(Season).filter_by(
        career_id=career_id,
        season_number=career.current_season_number,
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    # Validate count
    if len(request.player_ids) != playing_squad:
        raise HTTPException(
            status_code=400,
            detail=f"Must register exactly {playing_squad} players, got {len(request.player_ids)}",
        )

    # Validate uniqueness
    if len(set(request.player_ids)) != len(request.player_ids):
        raise HTTPException(status_code=400, detail="Duplicate player IDs not allowed")

    # Validate all players belong to user's team
    players = db.query(Player).filter(
        Player.id.in_(request.player_ids),
        Player.team_id == career.user_team_id,
    ).all()

    if len(players) != len(request.player_ids):
        raise HTTPException(
            status_code=400,
            detail="Some players not found or don't belong to your team",
        )

    # Validate at least 1 wicket keeper
    from app.models.player import PlayerRole
    wk_count = sum(1 for p in players if p.role == PlayerRole.WICKET_KEEPER)
    if wk_count < 1:
        raise HTTPException(
            status_code=400,
            detail="Must include at least 1 wicket keeper in registered squad",
        )

    # Validate overseas limit
    max_overseas = tier_config.get("max_overseas", 4)
    overseas_count = sum(1 for p in players if p.is_overseas)
    if overseas_count > max_overseas:
        raise HTTPException(
            status_code=400,
            detail=f"Max {max_overseas} overseas players allowed, got {overseas_count}",
        )

    # Save registration
    register_squad_for_team(
        db, career.id, season.id, career.user_team_id, request.player_ids,
    )

    # Auto-select best playing XI from the registered 15
    xi = _pick_best_xi(players)
    db.query(PlayingXI).filter_by(
        team_id=career.user_team_id,
        season_id=season.id,
    ).delete()
    for pos, player in enumerate(xi, 1):
        db.add(PlayingXI(
            team_id=career.user_team_id,
            season_id=season.id,
            player_id=player.id,
            position=pos,
        ))

    db.commit()

    return SquadRegistrationResponse(
        registered_player_ids=request.player_ids,
        registered_count=len(request.player_ids),
        max_allowed=playing_squad,
        is_complete=True,
        tier=tier,
    )
