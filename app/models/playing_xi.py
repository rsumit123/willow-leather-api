from sqlalchemy import Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PlayingXI(Base):
    __tablename__ = "playing_xi"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    position: Mapped[int] = mapped_column(Integer)  # 1-11 batting order

    team = relationship("Team")
    season = relationship("Season")
    player = relationship("Player")

    __table_args__ = (
        UniqueConstraint('team_id', 'season_id', 'player_id', name='unique_player_xi'),
    )

    def __repr__(self):
        return f"<PlayingXI team={self.team_id} season={self.season_id} player={self.player_id} pos={self.position}>"
