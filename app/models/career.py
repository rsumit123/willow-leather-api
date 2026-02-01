"""
Career and Season models for persistent game state
"""
from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, Enum, DateTime, Boolean, Text
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
    COMPLETED = "completed"  # Career ended


class SeasonPhase(enum.Enum):
    NOT_STARTED = "not_started"
    AUCTION = "auction"
    LEAGUE_STAGE = "league_stage"
    PLAYOFFS = "playoffs"
    COMPLETED = "completed"


class Career(Base):
    """
    Represents a single career playthrough.
    A career spans multiple seasons with the same teams.
    """
    __tablename__ = "careers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))  # Career save name
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Current state
    status: Mapped[CareerStatus] = mapped_column(Enum(CareerStatus), default=CareerStatus.SETUP)
    current_season_number: Mapped[int] = mapped_column(Integer, default=1)

    # User's team
    user_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    user_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[user_team_id])

    # Relationships
    seasons: Mapped[List["Season"]] = relationship("Season", back_populates="career", order_by="Season.season_number")

    def __repr__(self):
        return f"<Career '{self.name}' - Season {self.current_season_number}>"


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
