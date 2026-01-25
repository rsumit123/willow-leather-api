"""
Pydantic schemas for API request/response models
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


# Enums
class CareerStatusEnum(str, Enum):
    SETUP = "setup"
    PRE_AUCTION = "pre_auction"
    AUCTION = "auction"
    PRE_SEASON = "pre_season"
    IN_SEASON = "in_season"
    PLAYOFFS = "playoffs"
    POST_SEASON = "post_season"
    COMPLETED = "completed"


class SeasonPhaseEnum(str, Enum):
    NOT_STARTED = "not_started"
    AUCTION = "auction"
    LEAGUE_STAGE = "league_stage"
    PLAYOFFS = "playoffs"
    COMPLETED = "completed"


# Team Schemas
class TeamBase(BaseModel):
    name: str
    short_name: str
    city: str
    home_ground: str
    primary_color: str
    secondary_color: str


class TeamResponse(TeamBase):
    id: int
    budget: int
    remaining_budget: int
    is_user_team: bool

    class Config:
        from_attributes = True


class TeamChoice(BaseModel):
    index: int
    name: str
    short_name: str
    city: str


# Player Schemas
class PlayerBase(BaseModel):
    name: str
    age: int
    nationality: str
    is_overseas: bool
    role: str
    batting: int
    bowling: int
    overall_rating: int


class PlayerResponse(PlayerBase):
    id: int
    team_id: Optional[int] = None
    base_price: int
    sold_price: Optional[int] = None
    form: float
    batting_style: str
    bowling_type: str

    class Config:
        from_attributes = True


class PlayerBrief(BaseModel):
    id: int
    name: str
    role: str
    overall_rating: int
    is_overseas: bool
    base_price: int

    class Config:
        from_attributes = True


# Career Schemas
class CareerCreate(BaseModel):
    name: str
    team_index: int  # 0-7 for team selection


class CareerResponse(BaseModel):
    id: int
    name: str
    status: CareerStatusEnum
    current_season_number: int
    user_team_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CareerDetail(CareerResponse):
    user_team: Optional[TeamResponse] = None


# Season Schemas
class SeasonResponse(BaseModel):
    id: int
    season_number: int
    phase: SeasonPhaseEnum
    current_match_number: int
    total_league_matches: int
    champion_team_id: Optional[int] = None

    class Config:
        from_attributes = True


# Auction Schemas
class AuctionStateResponse(BaseModel):
    status: str
    current_player: Optional[PlayerBrief] = None
    current_bid: int
    current_bidder_team_id: Optional[int] = None
    current_bidder_team_name: Optional[str] = None
    players_sold: int
    players_unsold: int
    total_players: int


class TeamAuctionStateResponse(BaseModel):
    team_id: int
    team_name: str
    remaining_budget: int
    total_players: int
    overseas_players: int
    batsmen: int
    bowlers: int
    all_rounders: int
    wicket_keepers: int
    max_bid_possible: int


class BidRequest(BaseModel):
    pass  # User just needs to indicate they want to bid


class BidResponse(BaseModel):
    success: bool
    new_bid: int
    bidder_team_id: int
    bidder_team_name: str


class AuctionPlayerResult(BaseModel):
    player_id: int
    player_name: str
    is_sold: bool
    sold_to_team_id: Optional[int] = None
    sold_to_team_name: Optional[str] = None
    sold_price: int
    bid_history: list[dict]


# Fixture/Match Schemas
class FixtureResponse(BaseModel):
    id: int
    match_number: int
    fixture_type: str
    team1_id: int
    team1_name: str
    team2_id: int
    team2_name: str
    venue: str
    status: str
    winner_id: Optional[int] = None
    result_summary: Optional[str] = None

    class Config:
        from_attributes = True


class MatchResultResponse(BaseModel):
    fixture_id: int
    winner_id: Optional[int] = None
    winner_name: Optional[str] = None
    margin: str
    innings1_score: str
    innings2_score: str


# Standing Schemas
class StandingResponse(BaseModel):
    position: int
    team_id: int
    team_name: str
    team_short_name: str
    played: int
    won: int
    lost: int
    no_result: int
    points: int
    nrr: float


# Squad Schemas
class SquadResponse(BaseModel):
    team: TeamResponse
    players: list[PlayerResponse]
    total_players: int
    overseas_count: int
