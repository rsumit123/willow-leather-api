from sqlalchemy import String, Integer, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    career_id: Mapped[Optional[int]] = mapped_column(ForeignKey("careers.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str] = mapped_column(String(5))  # e.g., "MI", "CSK"
    city: Mapped[str] = mapped_column(String(50))
    home_ground: Mapped[str] = mapped_column(String(100))

    # Branding
    primary_color: Mapped[str] = mapped_column(String(7))  # Hex color
    secondary_color: Mapped[str] = mapped_column(String(7))

    # Finances
    budget: Mapped[int] = mapped_column(BigInteger, default=900000000)  # 90 crore default
    remaining_budget: Mapped[int] = mapped_column(BigInteger, default=900000000)

    # Season stats
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    no_results: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    net_run_rate: Mapped[float] = mapped_column(default=0.0)

    # Is this team controlled by the human player?
    is_user_team: Mapped[bool] = mapped_column(default=False)

    # Relationships
    players: Mapped[list["Player"]] = relationship("Player", back_populates="team")

    @property
    def squad_size(self) -> int:
        return len(self.players)

    @property
    def overseas_count(self) -> int:
        return sum(1 for p in self.players if p.is_overseas)

    def __repr__(self):
        return f"<Team {self.name} ({self.short_name})>"
