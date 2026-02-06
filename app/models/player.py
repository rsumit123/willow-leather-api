from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
import json
from app.database import Base


class PlayerRole(enum.Enum):
    BATSMAN = "batsman"
    BOWLER = "bowler"
    ALL_ROUNDER = "all_rounder"
    WICKET_KEEPER = "wicket_keeper"


class PlayerTrait(enum.Enum):
    CLUTCH = "clutch"           # +10 skill when runs < 20 or RRR > 10
    CHOKER = "choker"           # -15 skill in pressure situations
    BUCKET_HANDS = "bucket_hands"  # +20 catching success
    PARTNERSHIP_BREAKER = "partnership_breaker"  # +10 bowling after 50+ partnership
    FINISHER = "finisher"       # +15 batting in last 5 overs


class BowlingType(enum.Enum):
    PACE = "pace"
    MEDIUM = "medium"
    OFF_SPIN = "off_spin"
    LEG_SPIN = "leg_spin"
    LEFT_ARM_SPIN = "left_arm_spin"
    NONE = "none"


class BattingStyle(enum.Enum):
    RIGHT_HANDED = "right_handed"
    LEFT_HANDED = "left_handed"


class BattingIntent(enum.Enum):
    ANCHOR = "anchor"                 # Low variance, consistent 120-130 SR
    ACCUMULATOR = "accumulator"       # Moderate variance, 130-140 SR
    AGGRESSIVE = "aggressive"         # High variance, 140-160 SR
    POWER_HITTER = "power_hitter"     # Very high variance, boom or bust


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int] = mapped_column(Integer)
    nationality: Mapped[str] = mapped_column(String(50))
    is_overseas: Mapped[bool] = mapped_column(default=False)

    # Role and style
    role: Mapped[PlayerRole] = mapped_column(Enum(PlayerRole))
    batting_style: Mapped[BattingStyle] = mapped_column(Enum(BattingStyle))
    bowling_type: Mapped[BowlingType] = mapped_column(Enum(BowlingType))

    # Core attributes (1-100 scale)
    batting: Mapped[int] = mapped_column(Integer)  # Overall batting ability
    bowling: Mapped[int] = mapped_column(Integer)  # Overall bowling ability
    fielding: Mapped[int] = mapped_column(Integer)  # Catching, ground fielding
    fitness: Mapped[int] = mapped_column(Integer)  # Stamina, injury resistance

    # Batting sub-attributes
    power: Mapped[int] = mapped_column(Integer)  # Six-hitting ability
    technique: Mapped[int] = mapped_column(Integer)  # Defense, playing swing/spin
    running: Mapped[int] = mapped_column(Integer)  # Running between wickets

    # Bowling sub-attributes (relevant if bowler)
    pace_or_spin: Mapped[int] = mapped_column(Integer)  # Speed for pacers, turn for spinners
    accuracy: Mapped[int] = mapped_column(Integer)  # Line and length consistency
    variation: Mapped[int] = mapped_column(Integer)  # Slower balls, googlies etc.

    # Mental attributes
    temperament: Mapped[int] = mapped_column(Integer)  # Handling pressure
    consistency: Mapped[int] = mapped_column(Integer)  # Match-to-match reliability

    # Current state
    form: Mapped[float] = mapped_column(Float, default=1.0)  # 0.7-1.3 multiplier
    traits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    batting_intent: Mapped[str] = mapped_column(String(20), default=BattingIntent.ACCUMULATOR.value)  # Batting style intent

    # Team relationship
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team: Mapped["Team"] = relationship("Team", back_populates="players")

    # DNA attributes (v2 engine)
    batting_dna_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON BatterDNA
    bowler_dna_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON PacerDNA/SpinnerDNA

    # Auction
    base_price: Mapped[int] = mapped_column(Integer, default=2000000)  # In INR
    sold_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    @property
    def batting_dna(self):
        """Deserialize BatterDNA from JSON."""
        if not self.batting_dna_json:
            return None
        try:
            from app.engine.dna import BatterDNA
            return BatterDNA.from_dict(json.loads(self.batting_dna_json))
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def bowler_dna(self):
        """Deserialize PacerDNA or SpinnerDNA from JSON."""
        if not self.bowler_dna_json:
            return None
        try:
            from app.engine.dna import bowler_dna_from_dict
            return bowler_dna_from_dict(json.loads(self.bowler_dna_json))
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def overall_rating(self) -> int:
        """Calculate overall rating based on role"""
        if self.role == PlayerRole.BATSMAN:
            return int(self.batting * 0.7 + self.fielding * 0.2 + self.fitness * 0.1)
        elif self.role == PlayerRole.BOWLER:
            return int(self.bowling * 0.7 + self.fielding * 0.2 + self.fitness * 0.1)
        elif self.role == PlayerRole.ALL_ROUNDER:
            return int(self.batting * 0.4 + self.bowling * 0.4 + self.fielding * 0.1 + self.fitness * 0.1)
        elif self.role == PlayerRole.WICKET_KEEPER:
            return int(self.batting * 0.5 + self.fielding * 0.4 + self.fitness * 0.1)
        return 50

    def __repr__(self):
        return f"<Player {self.name} ({self.role.value}) - OVR: {self.overall_rating}>"
