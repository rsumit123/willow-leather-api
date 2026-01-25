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
    batting_style: str
    bowling_type: str

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


class SkipCategoryPlayerResult(BaseModel):
    player_id: int
    player_name: str
    is_sold: bool
    sold_to_team_id: Optional[int] = None
    sold_to_team_name: Optional[str] = None
    sold_price: int


class SkipCategoryResponse(BaseModel):
    players_auctioned: int
    results: list[SkipCategoryPlayerResult]


class SoldPlayerBrief(BaseModel):
    id: int
    name: str
    role: str
    overall_rating: int
    is_overseas: bool
    base_price: int
    sold_price: int
    sold_to_team_name: str

    class Config:
        from_attributes = True


class CategoryPlayersResponse(BaseModel):
    current_category: Optional[str] = None
    current_player_id: Optional[int] = None
    categories: dict[str, list[PlayerBrief]]
    counts: dict[str, int]
    sold: dict[str, list[SoldPlayerBrief]]
    sold_counts: dict[str, int]


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


# Interactive Match Schemas
class PlayerStateBrief(BaseModel):
    id: int
    name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    is_out: bool = False
    is_settled: bool = False
    is_nervous: bool = False
    is_on_fire: bool = False


class BowlerStateBrief(BaseModel):
    id: int
    name: str
    overs: int = 0
    balls: int = 0
    runs: int = 0
    wickets: int = 0
    is_tired: bool = False
    has_confidence: bool = False


class MatchStateResponse(BaseModel):
    innings: int
    runs: int
    wickets: int
    overs: str
    run_rate: float
    required_rate: Optional[float] = None
    target: Optional[int] = None

    striker: Optional[PlayerStateBrief] = None
    non_striker: Optional[PlayerStateBrief] = None
    bowler: Optional[BowlerStateBrief] = None

    pitch_type: str
    is_pressure: bool
    is_collapse: bool
    partnership_runs: int

    this_over: list[str]
    last_ball_commentary: Optional[str] = None

    phase: str
    balls_remaining: int
    status: str  # in_progress, completed
    winner_name: Optional[str] = None
    margin: Optional[str] = None

    # Team clarity fields
    batting_team_name: str = ""
    bowling_team_name: str = ""
    is_user_batting: bool = False
    user_team_name: str = ""

    # Innings change indicator
    innings_just_changed: bool = False


class BallRequest(BaseModel):
    aggression: str  # defend, balanced, attack


class TossResultResponse(BaseModel):
    toss_winner_id: int
    toss_winner_name: str
    user_won_toss: bool
    user_team_name: str


class StartMatchRequest(BaseModel):
    toss_winner_id: int
    elected_to: str  # "bat" or "bowl"


class BallResultResponse(BaseModel):
    outcome: str
    runs: int
    is_wicket: bool
    is_boundary: bool
    is_six: bool
    commentary: str
    match_state: MatchStateResponse


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
