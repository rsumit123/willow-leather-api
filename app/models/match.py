from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.database import Base


class MatchStatus(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InningsStatus(enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DismissalType(enum.Enum):
    NOT_OUT = "not_out"
    BOWLED = "bowled"
    CAUGHT = "caught"
    LBW = "lbw"
    RUN_OUT = "run_out"
    STUMPED = "stumped"
    HIT_WICKET = "hit_wicket"
    CAUGHT_BEHIND = "caught_behind"


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Teams
    team1_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team2_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team1: Mapped["Team"] = relationship("Team", foreign_keys=[team1_id])
    team2: Mapped["Team"] = relationship("Team", foreign_keys=[team2_id])

    # Toss
    toss_winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    toss_decision: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # "bat" or "bowl"

    # Match info
    venue: Mapped[str] = mapped_column(String(100))
    match_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    match_number: Mapped[int] = mapped_column(Integer)  # Match number in season

    # Status
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)

    # Result
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Relationships
    innings: Mapped[List["Innings"]] = relationship("Innings", back_populates="match")

    def __repr__(self):
        return f"<Match {self.team1.short_name} vs {self.team2.short_name}>"


class Innings(Base):
    __tablename__ = "innings"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    match: Mapped["Match"] = relationship("Match", back_populates="innings")

    batting_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    bowling_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    batting_team: Mapped["Team"] = relationship("Team", foreign_keys=[batting_team_id])
    bowling_team: Mapped["Team"] = relationship("Team", foreign_keys=[bowling_team_id])

    innings_number: Mapped[int] = mapped_column(Integer)  # 1 or 2

    # Score
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    wickets: Mapped[int] = mapped_column(Integer, default=0)
    overs_completed: Mapped[int] = mapped_column(Integer, default=0)
    balls_in_current_over: Mapped[int] = mapped_column(Integer, default=0)
    extras: Mapped[int] = mapped_column(Integer, default=0)

    # Target (for 2nd innings)
    target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[InningsStatus] = mapped_column(Enum(InningsStatus), default=InningsStatus.NOT_STARTED)

    # Ball by ball
    ball_events: Mapped[List["BallEvent"]] = relationship("BallEvent", back_populates="innings")

    @property
    def overs_display(self) -> str:
        return f"{self.overs_completed}.{self.balls_in_current_over}"

    @property
    def run_rate(self) -> float:
        total_balls = self.overs_completed * 6 + self.balls_in_current_over
        if total_balls == 0:
            return 0.0
        return (self.total_runs / total_balls) * 6

    def __repr__(self):
        return f"<Innings {self.innings_number}: {self.total_runs}/{self.wickets} ({self.overs_display})>"


class BallEvent(Base):
    __tablename__ = "ball_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    innings_id: Mapped[int] = mapped_column(ForeignKey("innings.id"))
    innings: Mapped["Innings"] = relationship("Innings", back_populates="ball_events")

    over_number: Mapped[int] = mapped_column(Integer)
    ball_number: Mapped[int] = mapped_column(Integer)  # 1-6 (excluding extras)

    # Players involved
    batter_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    bowler_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    batter: Mapped["Player"] = relationship("Player", foreign_keys=[batter_id])
    bowler: Mapped["Player"] = relationship("Player", foreign_keys=[bowler_id])

    # Outcome
    runs_scored: Mapped[int] = mapped_column(Integer, default=0)
    is_boundary: Mapped[bool] = mapped_column(default=False)
    is_six: Mapped[bool] = mapped_column(default=False)

    # Extras
    is_wide: Mapped[bool] = mapped_column(default=False)
    is_no_ball: Mapped[bool] = mapped_column(default=False)
    is_bye: Mapped[bool] = mapped_column(default=False)
    is_leg_bye: Mapped[bool] = mapped_column(default=False)
    extra_runs: Mapped[int] = mapped_column(Integer, default=0)

    # Wicket
    is_wicket: Mapped[bool] = mapped_column(default=False)
    dismissal_type: Mapped[Optional[DismissalType]] = mapped_column(Enum(DismissalType), nullable=True)
    dismissed_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    fielder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)

    # Commentary
    commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<Ball {self.over_number}.{self.ball_number}: {self.runs_scored} runs>"
