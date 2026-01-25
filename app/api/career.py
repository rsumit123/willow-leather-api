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
from app.generators import PlayerGenerator, TeamGenerator
from app.api.schemas import (
    CareerCreate, CareerResponse, CareerDetail, TeamChoice, TeamResponse,
    SquadResponse, PlayerResponse
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
