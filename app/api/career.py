"""
Career management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_session
from app.models.career import Career, Season, CareerStatus, SeasonPhase
from app.models.team import Team
from app.models.player import Player
from app.models.auction import Auction, AuctionStatus
from app.models.playing_xi import PlayingXI
from app.generators import PlayerGenerator, TeamGenerator
from app.validators.playing_xi_validator import PlayingXIValidator
from app.api.schemas import (
    CareerCreate, CareerResponse, CareerDetail, TeamChoice, TeamResponse,
    SquadResponse, PlayerResponse, PlayingXIRequest, PlayingXIPlayerResponse,
    PlayingXIResponse, PlayingXIValidationResponse
)

router = APIRouter(prefix="/career", tags=["Career"])


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
def create_career(career_data: CareerCreate, db: Session = Depends(get_db)):
    """
    Create a new career.
    This will:
    1. Create the career record
    2. Create all 8 teams (with user's selected team marked)
    3. Generate player pool for auction
    4. Create first season
    """
    # Validate team index
    if career_data.team_index < 0 or career_data.team_index > 7:
        raise HTTPException(status_code=400, detail="Team index must be 0-7")

    # Create career
    career = Career(
        name=career_data.name,
        status=CareerStatus.PRE_AUCTION,
    )
    db.add(career)
    db.flush()  # Get career ID

    # Create teams for this career
    teams = TeamGenerator.create_teams(career_id=career.id, user_team_index=career_data.team_index)
    for team in teams:
        db.add(team)
    db.flush()

    # Set user's team
    user_team = next(t for t in teams if t.is_user_team)
    career.user_team_id = user_team.id

    # Generate players
    players = PlayerGenerator.generate_player_pool(150)
    for player in players:
        db.add(player)

    # Create first season
    season = Season(
        career_id=career.id,
        season_number=1,
        phase=SeasonPhase.NOT_STARTED,
    )
    db.add(season)

    # Create auction for the season
    db.flush()
    auction = Auction(
        season_id=season.id,
        status=AuctionStatus.NOT_STARTED,
    )
    db.add(auction)

    db.commit()
    db.refresh(career)

    return CareerDetail(
        id=career.id,
        name=career.name,
        status=CareerStatus(career.status.value),
        current_season_number=career.current_season_number,
        user_team_id=career.user_team_id,
        created_at=career.created_at,
        user_team=TeamResponse.model_validate(user_team) if user_team else None,
    )


@router.get("/list", response_model=List[CareerResponse])
def list_careers(db: Session = Depends(get_db)):
    """List all saved careers"""
    careers = db.query(Career).order_by(Career.updated_at.desc()).all()
    return [CareerResponse.model_validate(c) for c in careers]


@router.get("/{career_id}", response_model=CareerDetail)
def get_career(career_id: int, db: Session = Depends(get_db)):
    """Get career details"""
    career = db.query(Career).filter_by(id=career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    user_team = db.query(Team).filter_by(id=career.user_team_id).first()

    return CareerDetail(
        id=career.id,
        name=career.name,
        status=CareerStatus(career.status.value),
        current_season_number=career.current_season_number,
        user_team_id=career.user_team_id,
        created_at=career.created_at,
        user_team=TeamResponse.model_validate(user_team) if user_team else None,
    )


@router.delete("/{career_id}")
def delete_career(career_id: int, db: Session = Depends(get_db)):
    """Delete a career (and all associated data)"""
    career = db.query(Career).filter_by(id=career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # This would need cascade deletes set up properly
    # For now, just delete the career
    db.delete(career)
    db.commit()

    return {"message": "Career deleted"}


@router.get("/{career_id}/teams", response_model=List[TeamResponse])
def get_career_teams(career_id: int, db: Session = Depends(get_db)):
    """Get all teams in a career"""
    career = db.query(Career).filter_by(id=career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    teams = db.query(Team).filter_by(career_id=career_id).all()
    return [TeamResponse.model_validate(t) for t in teams]


@router.get("/{career_id}/teams/{team_id}/squad", response_model=SquadResponse)
def get_team_squad(career_id: int, team_id: int, db: Session = Depends(get_db)):
    """Get a team's squad"""
    career = db.query(Career).filter_by(id=career_id).first()
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
        ))

    return SquadResponse(
        team=TeamResponse.model_validate(team),
        players=player_responses,
        total_players=len(players),
        overseas_count=sum(1 for p in players if p.is_overseas),
    )


@router.get("/{career_id}/playing-xi", response_model=PlayingXIResponse)
def get_playing_xi(career_id: int, db: Session = Depends(get_db)):
    """Get user team's playing XI"""
    career = db.query(Career).filter_by(id=career_id).first()
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
            position=entry.position,
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
def set_playing_xi(career_id: int, request: PlayingXIRequest, db: Session = Depends(get_db)):
    """Set user team's playing XI (validates before saving)"""
    career = db.query(Career).filter_by(id=career_id).first()
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
            position=entry.position,
        ))

    return PlayingXIResponse(
        players=player_responses,
        is_valid=True,
        is_set=True,
    )


@router.post("/{career_id}/playing-xi/validate", response_model=PlayingXIValidationResponse)
def validate_playing_xi(career_id: int, request: PlayingXIRequest, db: Session = Depends(get_db)):
    """Validate proposed XI without saving (for real-time feedback)"""
    career = db.query(Career).filter_by(id=career_id).first()
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
