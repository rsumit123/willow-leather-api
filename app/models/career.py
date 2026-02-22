"""
Career and Season models for persistent game state
"""
from typing import Optional, List
from sqlalchemy import String, Integer, Float, ForeignKey, Enum, DateTime, Boolean, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.database import Base


class CareerStatus(enum.Enum):
    SETUP = "setup"  # Initial setup, team selection
    PRE_AUCTION = "pre_auction"  # Before auction starts
    AUCTION = "auction"  # Auction in progress
    PRE_SEASON = "pre_season"  # After auction, before matches
    IN_SEASON = "in_season"  # Matches being played
    PLAYOFFS = "playoffs"  # Playoff stage
    POST_SEASON = "post_season"  # Season ended, before next
    TRANSFER_WINDOW = "transfer_window"  # Transfer window between seasons
    COMPLETED = "completed"  # Career ended


class SeasonPhase(enum.Enum):
    NOT_STARTED = "not_started"
    AUCTION = "auction"
    LEAGUE_STAGE = "league_stage"
    PLAYOFFS = "playoffs"
    COMPLETED = "completed"
    TRANSFER_WINDOW = "transfer_window"


class CareerTier(enum.Enum):
    DISTRICT = "district"
    STATE = "state"
    IPL = "ipl"


class DayType(enum.Enum):
    MATCH_DAY = "match_day"
    TRAINING = "training"
    REST = "rest"
    TRAVEL = "travel"
    EVENT = "event"


class NotificationType(enum.Enum):
    BOARD_OBJECTIVE = "board_objective"
    MATCH_RESULT = "match_result"
    INJURY = "injury"
    PROMOTION = "promotion"
    SACKED = "sacked"
    TRANSFER = "transfer"
    MILESTONE = "milestone"
    TRAINING = "training"


class DrillType(enum.Enum):
    NETS_BATTING = "nets_batting"
    BOWLING_PRACTICE = "bowling_practice"
    FIELDING_DRILLS = "fielding_drills"
    FITNESS_CAMP = "fitness_camp"
    SPIN_WORKSHOP = "spin_workshop"
    PACE_HANDLING = "pace_handling"
    POWER_HITTING = "power_hitting"
    DEATH_BOWLING = "death_bowling"


class Career(Base):
    """
    Represents a single career playthrough.
    A career spans multiple seasons with the same teams.
    Each career belongs to a user (max 3 per user).
    """
    __tablename__ = "careers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))  # Career save name
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Owner
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    user: Mapped["User"] = relationship("User", back_populates="careers")

    # Current state
    status: Mapped[CareerStatus] = mapped_column(Enum(CareerStatus), default=CareerStatus.SETUP)
    current_season_number: Mapped[int] = mapped_column(Integer, default=1)

    # Tier progression
    tier: Mapped[str] = mapped_column(String(20), default="ipl")  # district, state, ipl
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    trophies_won: Mapped[int] = mapped_column(Integer, default=0)
    seasons_played: Mapped[int] = mapped_column(Integer, default=0)
    promoted_at_season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    game_over: Mapped[bool] = mapped_column(Boolean, default=False)
    game_over_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # User's team
    user_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    user_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[user_team_id])

    # Relationships
    seasons: Mapped[List["Season"]] = relationship("Season", back_populates="career", order_by="Season.season_number")

    def __repr__(self):
        return f"<Career '{self.name}' - {self.tier} Season {self.current_season_number}>"


class Season(Base):
    """
    Represents a single season within a career.
    Contains all matches, standings, and results for that season.
    """
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id"))
    career: Mapped["Career"] = relationship("Career", back_populates="seasons")

    season_number: Mapped[int] = mapped_column(Integer)  # 1, 2, 3, etc.
    phase: Mapped[SeasonPhase] = mapped_column(Enum(SeasonPhase), default=SeasonPhase.NOT_STARTED)

    # Auction state
    auction_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Season progress
    current_match_number: Mapped[int] = mapped_column(Integer, default=0)
    total_league_matches: Mapped[int] = mapped_column(Integer, default=56)  # 8 teams * 14 matches / 2

    # Champion
    champion_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    runner_up_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)

    # Relationships
    fixtures: Mapped[List["Fixture"]] = relationship("Fixture", back_populates="season", order_by="Fixture.match_number")

    def __repr__(self):
        return f"<Season {self.season_number} - {self.phase.value}>"


class FixtureType(enum.Enum):
    LEAGUE = "league"
    QUALIFIER_1 = "qualifier_1"
    ELIMINATOR = "eliminator"
    QUALIFIER_2 = "qualifier_2"
    FINAL = "final"


class FixtureStatus(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Fixture(Base):
    """
    A scheduled match in a season.
    Links to the actual Match record once played.
    """
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    season: Mapped["Season"] = relationship("Season", back_populates="fixtures")

    match_number: Mapped[int] = mapped_column(Integer)  # Order in season
    fixture_type: Mapped[FixtureType] = mapped_column(Enum(FixtureType), default=FixtureType.LEAGUE)

    # Teams
    team1_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team2_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team1: Mapped["Team"] = relationship("Team", foreign_keys=[team1_id])
    team2: Mapped["Team"] = relationship("Team", foreign_keys=[team2_id])

    # Venue
    venue: Mapped[str] = mapped_column(String(100))

    # Status
    status: Mapped[FixtureStatus] = mapped_column(Enum(FixtureStatus), default=FixtureStatus.SCHEDULED)

    # Result (after match is played)
    match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matches.id"), nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self):
        return f"<Fixture #{self.match_number}: {self.team1.short_name if self.team1 else '?'} vs {self.team2.short_name if self.team2 else '?'}>"


class TeamSeasonStats(Base):
    """
    Team statistics for a specific season.
    Separate from Team model to preserve historical data.
    """
    __tablename__ = "team_season_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    # League standings
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    no_results: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)

    # Net Run Rate components
    runs_scored: Mapped[int] = mapped_column(Integer, default=0)
    overs_faced: Mapped[float] = mapped_column(default=0.0)
    runs_conceded: Mapped[int] = mapped_column(Integer, default=0)
    overs_bowled: Mapped[float] = mapped_column(default=0.0)

    @property
    def net_run_rate(self) -> float:
        """Calculate NRR: (runs scored / overs faced) - (runs conceded / overs bowled)"""
        if self.overs_faced == 0 or self.overs_bowled == 0:
            return 0.0
        scoring_rate = self.runs_scored / self.overs_faced
        conceding_rate = self.runs_conceded / self.overs_bowled
        return round(scoring_rate - conceding_rate, 3)

    def __repr__(self):
        return f"<TeamSeasonStats: {self.wins}W {self.losses}L, NRR: {self.net_run_rate:+.3f}>"


class PlayerSeasonStats(Base):
    """
    Player statistics for a specific season.
    Tracks batting, bowling, and fielding stats for leaderboards.
    """
    __tablename__ = "player_season_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    # Batting stats
    matches_batted: Mapped[int] = mapped_column(Integer, default=0)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    balls_faced: Mapped[int] = mapped_column(Integer, default=0)
    fours: Mapped[int] = mapped_column(Integer, default=0)
    sixes: Mapped[int] = mapped_column(Integer, default=0)
    highest_score: Mapped[int] = mapped_column(Integer, default=0)
    not_outs: Mapped[int] = mapped_column(Integer, default=0)

    # Bowling stats
    matches_bowled: Mapped[int] = mapped_column(Integer, default=0)
    wickets: Mapped[int] = mapped_column(Integer, default=0)
    overs_bowled: Mapped[float] = mapped_column(default=0.0)
    runs_conceded: Mapped[int] = mapped_column(Integer, default=0)
    best_bowling_wickets: Mapped[int] = mapped_column(Integer, default=0)
    best_bowling_runs: Mapped[int] = mapped_column(Integer, default=0)

    # Fielding stats
    catches: Mapped[int] = mapped_column(Integer, default=0)
    stumpings: Mapped[int] = mapped_column(Integer, default=0)
    run_outs: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    player: Mapped["Player"] = relationship("Player")
    team: Mapped["Team"] = relationship("Team")

    @property
    def batting_average(self) -> float:
        """Calculate batting average: runs / dismissals"""
        dismissals = self.matches_batted - self.not_outs
        if dismissals <= 0:
            return self.runs if self.runs > 0 else 0.0
        return round(self.runs / dismissals, 2)

    @property
    def strike_rate(self) -> float:
        """Calculate strike rate: (runs / balls) * 100"""
        if self.balls_faced == 0:
            return 0.0
        return round((self.runs / self.balls_faced) * 100, 2)

    @property
    def bowling_average(self) -> float:
        """Calculate bowling average: runs conceded / wickets"""
        if self.wickets == 0:
            return 0.0
        return round(self.runs_conceded / self.wickets, 2)

    @property
    def economy_rate(self) -> float:
        """Calculate economy rate: runs per over"""
        if self.overs_bowled == 0:
            return 0.0
        return round(self.runs_conceded / self.overs_bowled, 2)

    @property
    def best_bowling(self) -> str:
        """Format best bowling figures"""
        return f"{self.best_bowling_wickets}/{self.best_bowling_runs}"

    def __repr__(self):
        return f"<PlayerSeasonStats: {self.runs} runs, {self.wickets} wkts>"


class PlayerMatchStats(Base):
    """
    Individual player performance in a specific match.
    Used for form calculation and historical tracking.
    """
    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    # Batting
    runs_scored: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    balls_faced: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    fours: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    sixes: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    is_out: Mapped[bool] = mapped_column(Boolean, default=False, insert_default=False)
    dismissal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    dismissed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)

    # Bowling
    overs_bowled: Mapped[float] = mapped_column(Float, default=0.0, insert_default=0.0)
    runs_conceded: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    wickets_taken: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)

    # Fielding
    catches: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    stumpings: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)
    run_outs: Mapped[int] = mapped_column(Integer, default=0, insert_default=0)

    # Pre-computed form impact
    form_delta: Mapped[float] = mapped_column(Float, default=0.0, insert_default=0.0)

    # Relationships
    player: Mapped["Player"] = relationship("Player", foreign_keys=[player_id])
    match: Mapped["Match"] = relationship("Match")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure numeric fields default to 0 in Python (SQLAlchemy defaults only apply at INSERT time)
        for field, default in [
            ("runs_scored", 0), ("balls_faced", 0), ("fours", 0), ("sixes", 0),
            ("is_out", False), ("overs_bowled", 0.0), ("runs_conceded", 0),
            ("wickets_taken", 0), ("catches", 0), ("stumpings", 0),
            ("run_outs", 0), ("form_delta", 0.0),
        ]:
            if getattr(self, field, None) is None:
                setattr(self, field, default)

    def __repr__(self):
        return f"<PlayerMatchStats: {self.runs_scored}({self.balls_faced}) {self.wickets_taken}w>"


class MatchMatchup(Base):
    """
    Aggregated batter-vs-bowler data per matchup per innings.
    Used for post-match DNA matchup analysis cards.
    """
    __tablename__ = "match_matchups"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    innings_number: Mapped[int] = mapped_column(Integer)

    batter_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    bowler_id: Mapped[int] = mapped_column(ForeignKey("players.id"))

    # Aggregated stats
    balls_faced: Mapped[int] = mapped_column(Integer, default=0)
    runs_scored: Mapped[int] = mapped_column(Integer, default=0)
    fours: Mapped[int] = mapped_column(Integer, default=0)
    sixes: Mapped[int] = mapped_column(Integer, default=0)
    dots: Mapped[int] = mapped_column(Integer, default=0)

    # Dismissal
    was_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    wicket_delivery_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    exploited_weakness: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # DNA snapshots (frozen at match time)
    batter_dna_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bowler_dna_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    batter: Mapped["Player"] = relationship("Player", foreign_keys=[batter_id])
    bowler: Mapped["Player"] = relationship("Player", foreign_keys=[bowler_id])

    def __repr__(self):
        return f"<MatchMatchup: batter {self.batter_id} vs bowler {self.bowler_id} - {self.runs_scored}/{self.balls_faced}>"


class PlayerRetention(Base):
    """
    Records player retention decisions during transfer window.
    """
    __tablename__ = "player_retentions"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))

    retention_slot: Mapped[int] = mapped_column(Integer)  # 1-4
    retention_price: Mapped[int] = mapped_column(BigInteger)

    # Relationships
    player: Mapped["Player"] = relationship("Player")
    team: Mapped["Team"] = relationship("Team")

    def __repr__(self):
        return f"<PlayerRetention: slot {self.retention_slot} - {self.retention_price}>"


class GameDay(Base):
    """
    A single day in the game calendar. Maps to a date and an activity type.
    """
    __tablename__ = "game_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))

    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    day_type: Mapped[DayType] = mapped_column(Enum(DayType), default=DayType.REST)
    fixture_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    event_description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        return f"<GameDay {self.date}: {self.day_type.value}>"


class Notification(Base):
    """
    In-game notification for the manager inbox.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id"), index=True)

    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action_url: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<Notification: {self.title}>"


class TrainingSession(Base):
    """
    A training drill session on a training day.
    Provides temporary stat boosts to selected players.
    """
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    game_day_id: Mapped[int] = mapped_column(ForeignKey("game_days.id"))

    drill_type: Mapped[DrillType] = mapped_column(Enum(DrillType))
    player_ids_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of player IDs
    boost_attribute: Mapped[str] = mapped_column(String(50))  # "batting", "bowling", etc.
    boost_amount: Mapped[int] = mapped_column(Integer, default=2)
    boost_expires_after_matches: Mapped[int] = mapped_column(Integer, default=2)
    matches_remaining: Mapped[int] = mapped_column(Integer, default=2)

    def __repr__(self):
        return f"<TrainingSession: {self.drill_type.value} +{self.boost_amount}>"


class BoardObjective(Base):
    """
    Board objective for the current season.
    Defines what the manager must achieve and consequences.
    """
    __tablename__ = "board_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))

    description: Mapped[str] = mapped_column(String(200))
    target_type: Mapped[str] = mapped_column(String(50))  # "finish_position", "win_count", "win_trophy"
    target_value: Mapped[int] = mapped_column(Integer)
    achieved: Mapped[bool] = mapped_column(Boolean, default=False)
    consequence: Mapped[str] = mapped_column(String(50))  # "promotion", "stay", "sacked"

    def __repr__(self):
        return f"<BoardObjective: {self.description}>"


class SquadRegistration(Base):
    """
    Records a player registered in the playing squad for a season.
    At state tier, teams have 25 players but register 15 for the tournament.
    """
    __tablename__ = "squad_registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[int] = mapped_column(ForeignKey("careers.id", ondelete="CASCADE"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))

    # Relationships
    player: Mapped["Player"] = relationship("Player")
    team: Mapped["Team"] = relationship("Team")

    def __repr__(self):
        return f"<SquadRegistration team={self.team_id} player={self.player_id}>"
