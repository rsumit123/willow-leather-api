"""
Auction API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_session
from app.models.career import Career, Season, CareerStatus, SeasonPhase
from app.models.team import Team
from app.models.player import Player
from app.models.auction import (
    Auction, AuctionPlayerEntry, TeamAuctionState,
    AuctionStatus, AuctionPlayerStatus
)
from app.engine.auction_engine import AuctionEngine
from app.api.schemas import (
    AuctionStateResponse, TeamAuctionStateResponse, BidResponse,
    AuctionPlayerResult, PlayerBrief
)

router = APIRouter(prefix="/auction", tags=["Auction"])


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_auction(career_id: int, db: Session) -> tuple[Career, Season, Auction]:
    """Helper to get current auction"""
    career = db.query(Career).filter_by(id=career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    season = (
        db.query(Season)
        .filter_by(career_id=career_id, season_number=career.current_season_number)
        .first()
    )
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    auction = db.query(Auction).filter_by(season_id=season.id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    return career, season, auction


@router.post("/{career_id}/start")
def start_auction(career_id: int, db: Session = Depends(get_db)):
    """Start the auction for the current season"""
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.NOT_STARTED:
        raise HTTPException(status_code=400, detail="Auction already started or completed")

    # Get teams and players
    teams = db.query(Team).all()
    players = db.query(Player).filter_by(team_id=None).all()  # Unsold players

    if len(players) == 0:
        raise HTTPException(status_code=400, detail="No players available for auction")

    # Initialize auction
    engine = AuctionEngine(db, auction)
    engine.initialize_auction(teams, players)

    # Update career status
    career.status = CareerStatus.AUCTION
    season.phase = SeasonPhase.AUCTION
    db.commit()

    return {"message": "Auction started", "total_players": len(players)}


@router.get("/{career_id}/state", response_model=AuctionStateResponse)
def get_auction_state(career_id: int, db: Session = Depends(get_db)):
    """Get current auction state"""
    career, season, auction = get_current_auction(career_id, db)

    current_player = None
    current_bidder_name = None

    if auction.current_player_id:
        player = db.query(Player).filter_by(id=auction.current_player_id).first()
        if player:
            current_player = PlayerBrief(
                id=player.id,
                name=player.name,
                role=player.role.value,
                overall_rating=player.overall_rating,
                is_overseas=player.is_overseas,
                base_price=player.base_price,
            )

    if auction.current_bidder_team_id:
        team = db.query(Team).filter_by(id=auction.current_bidder_team_id).first()
        current_bidder_name = team.short_name if team else None

    return AuctionStateResponse(
        status=auction.status.value,
        current_player=current_player,
        current_bid=auction.current_bid,
        current_bidder_team_id=auction.current_bidder_team_id,
        current_bidder_team_name=current_bidder_name,
        players_sold=auction.players_sold,
        players_unsold=auction.players_unsold,
        total_players=auction.total_players,
    )


@router.get("/{career_id}/teams", response_model=List[TeamAuctionStateResponse])
def get_teams_auction_state(career_id: int, db: Session = Depends(get_db)):
    """Get all teams' auction state"""
    career, season, auction = get_current_auction(career_id, db)

    states = db.query(TeamAuctionState).filter_by(auction_id=auction.id).all()

    result = []
    for state in states:
        team = db.query(Team).filter_by(id=state.team_id).first()
        result.append(TeamAuctionStateResponse(
            team_id=state.team_id,
            team_name=team.short_name if team else "?",
            remaining_budget=state.remaining_budget,
            total_players=state.total_players,
            overseas_players=state.overseas_players,
            batsmen=state.batsmen,
            bowlers=state.bowlers,
            all_rounders=state.all_rounders,
            wicket_keepers=state.wicket_keepers,
            max_bid_possible=state.max_bid_possible,
        ))

    return result


@router.post("/{career_id}/next-player")
def next_player(career_id: int, db: Session = Depends(get_db)):
    """Move to next player in auction"""
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Auction not in progress")

    engine = AuctionEngine(db, auction)
    player_entry = engine.get_next_player()

    if not player_entry:
        # Auction complete
        engine.complete_auction()
        career.status = CareerStatus.PRE_SEASON
        season.phase = SeasonPhase.LEAGUE_STAGE
        season.auction_completed = True
        db.commit()
        return {"message": "Auction complete", "auction_finished": True}

    # Start bidding on this player
    engine.start_bidding(player_entry)

    player = player_entry.player
    return {
        "auction_finished": False,
        "player": PlayerBrief(
            id=player.id,
            name=player.name,
            role=player.role.value,
            overall_rating=player.overall_rating,
            is_overseas=player.is_overseas,
            base_price=player.base_price,
        ),
        "starting_bid": player.base_price,
    }


@router.post("/{career_id}/bid", response_model=BidResponse)
def place_user_bid(career_id: int, db: Session = Depends(get_db)):
    """Place a bid for the user's team"""
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Auction not in progress")

    if not auction.current_player_id:
        raise HTTPException(status_code=400, detail="No player currently being auctioned")

    engine = AuctionEngine(db, auction)
    user_team = db.query(Team).filter_by(is_user_team=True).first()

    if not user_team:
        raise HTTPException(status_code=400, detail="User team not found")

    # Check if user can bid
    state = engine.get_team_state(user_team.id)
    player = db.query(Player).filter_by(id=auction.current_player_id).first()

    next_bid = engine.get_next_bid_amount(auction.current_bid)

    if next_bid > state.max_bid_possible:
        raise HTTPException(status_code=400, detail="Cannot afford this bid")

    if player.is_overseas and state.overseas_players >= 8:
        raise HTTPException(status_code=400, detail="Overseas player limit reached")

    if state.total_players >= 25:
        raise HTTPException(status_code=400, detail="Squad is full")

    if auction.current_bidder_team_id == user_team.id:
        raise HTTPException(status_code=400, detail="Already highest bidder")

    # Place the bid
    success = engine.place_bid(user_team.id, player.id, next_bid)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to place bid")

    return BidResponse(
        success=True,
        new_bid=next_bid,
        bidder_team_id=user_team.id,
        bidder_team_name=user_team.short_name,
    )


@router.post("/{career_id}/pass")
def pass_bidding(career_id: int, db: Session = Depends(get_db)):
    """User passes on current bidding (lets AI continue)"""
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Auction not in progress")

    if not auction.current_player_id:
        raise HTTPException(status_code=400, detail="No player currently being auctioned")

    return {"message": "Passed"}


@router.post("/{career_id}/simulate-bidding")
def simulate_bidding_round(career_id: int, db: Session = Depends(get_db)):
    """
    Simulate one round of AI bidding.
    Call this repeatedly until bidding is complete.
    """
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Auction not in progress")

    if not auction.current_player_id:
        raise HTTPException(status_code=400, detail="No player currently being auctioned")

    engine = AuctionEngine(db, auction)
    user_team = db.query(Team).filter_by(is_user_team=True).first()
    player = db.query(Player).filter_by(id=auction.current_player_id).first()

    # Run one bidding round (AI only)
    new_bid, bidder_id = engine.run_bidding_round(
        db.query(AuctionPlayerEntry).filter_by(
            auction_id=auction.id,
            player_id=player.id
        ).first(),
        user_team.id,
        user_bids=False
    )

    if bidder_id:
        team = db.query(Team).filter_by(id=bidder_id).first()
        return {
            "bid_placed": True,
            "new_bid": new_bid,
            "bidder_team_id": bidder_id,
            "bidder_team_name": team.short_name if team else "?",
            "bidding_complete": False,
        }
    else:
        return {
            "bid_placed": False,
            "new_bid": auction.current_bid,
            "bidder_team_id": auction.current_bidder_team_id,
            "bidding_complete": False,  # Let frontend decide when to finalize
        }


@router.post("/{career_id}/finalize-player", response_model=AuctionPlayerResult)
def finalize_current_player(career_id: int, db: Session = Depends(get_db)):
    """Finalize bidding on current player (sold or unsold)"""
    career, season, auction = get_current_auction(career_id, db)

    if auction.status != AuctionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Auction not in progress")

    if not auction.current_player_id:
        raise HTTPException(status_code=400, detail="No player currently being auctioned")

    engine = AuctionEngine(db, auction)
    player_entry = db.query(AuctionPlayerEntry).filter_by(
        auction_id=auction.id,
        player_id=auction.current_player_id
    ).first()

    result = engine.finalize_player(player_entry)

    return AuctionPlayerResult(
        player_id=result.player.id,
        player_name=result.player.name,
        is_sold=result.is_sold,
        sold_to_team_id=result.winning_team.id if result.winning_team else None,
        sold_to_team_name=result.winning_team.short_name if result.winning_team else None,
        sold_price=result.winning_bid,
        bid_history=result.bid_history,
    )


@router.post("/{career_id}/auto-complete")
def auto_complete_auction(career_id: int, db: Session = Depends(get_db)):
    """
    Auto-complete the entire auction (for testing or if user wants to skip).
    Simulates all remaining bidding.
    """
    career, season, auction = get_current_auction(career_id, db)

    if auction.status == AuctionStatus.NOT_STARTED:
        # Start it first
        teams = db.query(Team).all()
        players = db.query(Player).filter_by(team_id=None).all()
        engine = AuctionEngine(db, auction)
        engine.initialize_auction(teams, players)

    if auction.status == AuctionStatus.COMPLETED:
        return {"message": "Auction already completed"}

    engine = AuctionEngine(db, auction)
    user_team = db.query(Team).filter_by(is_user_team=True).first()

    results = []

    while not engine.is_auction_complete():
        player_entry = engine.get_next_player()
        if not player_entry:
            break

        engine.start_bidding(player_entry)

        # Simulate all bidding for this player
        engine.simulate_full_bidding(player_entry, user_team.id)

        # Finalize
        result = engine.finalize_player(player_entry)
        results.append({
            "player": result.player.name,
            "sold": result.is_sold,
            "team": result.winning_team.short_name if result.winning_team else None,
            "price": result.winning_bid,
        })

    engine.complete_auction()
    career.status = CareerStatus.PRE_SEASON
    season.phase = SeasonPhase.LEAGUE_STAGE
    season.auction_completed = True
    db.commit()

    return {
        "message": "Auction completed",
        "players_sold": auction.players_sold,
        "players_unsold": auction.players_unsold,
        "results": results[:20],  # Return first 20 for brevity
    }
