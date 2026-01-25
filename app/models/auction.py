"""
Auction models for IPL-style player auction
"""
from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, Enum, DateTime, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.database import Base


class AuctionStatus(enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"


class AuctionPlayerStatus(enum.Enum):
    AVAILABLE = "available"
    IN_BIDDING = "in_bidding"
    SOLD = "sold"
    UNSOLD = "unsold"


class AuctionCategory(enum.Enum):
    MARQUEE = "marquee"           # OVR >= 80
    BATSMEN = "batsmen"
    BOWLERS = "bowlers"
    ALL_ROUNDERS = "all_rounders"
    WICKET_KEEPERS = "wicket_keepers"


class Auction(Base):
    """
    Represents an auction event for a season.
    """
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))

    status: Mapped[AuctionStatus] = mapped_column(Enum(AuctionStatus), default=AuctionStatus.NOT_STARTED)

    # Current bidding state
    current_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    current_bid: Mapped[int] = mapped_column(BigInteger, default=0)
    current_bidder_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)

    # Auction rules
    salary_cap: Mapped[int] = mapped_column(BigInteger, default=900000000)  # 90 crore
    min_squad_size: Mapped[int] = mapped_column(Integer, default=18)
    max_squad_size: Mapped[int] = mapped_column(Integer, default=25)
    max_overseas: Mapped[int] = mapped_column(Integer, default=8)

    # Progress tracking
    players_sold: Mapped[int] = mapped_column(Integer, default=0)
    players_unsold: Mapped[int] = mapped_column(Integer, default=0)
    total_players: Mapped[int] = mapped_column(Integer, default=0)

    # Category tracking
    current_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    bids: Mapped[List["AuctionBid"]] = relationship("AuctionBid", back_populates="auction")
    player_entries: Mapped[List["AuctionPlayerEntry"]] = relationship("AuctionPlayerEntry", back_populates="auction")

    def __repr__(self):
        return f"<Auction {self.status.value} - {self.players_sold} sold>"


class AuctionPlayerEntry(Base):
    """
    Tracks a player's status in the auction.
    """
    __tablename__ = "auction_player_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auctions.id"))
    auction: Mapped["Auction"] = relationship("Auction", back_populates="player_entries")

    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    player: Mapped["Player"] = relationship("Player")

    # Auction order (lower = earlier in auction)
    auction_order: Mapped[int] = mapped_column(Integer)

    # Status
    status: Mapped[AuctionPlayerStatus] = mapped_column(Enum(AuctionPlayerStatus), default=AuctionPlayerStatus.AVAILABLE)

    # Category (marquee, batsmen, bowlers, all_rounders, wicket_keepers)
    category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Result
    sold_to_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    sold_price: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Set (for multi-round auctions)
    auction_set: Mapped[int] = mapped_column(Integer, default=1)  # 1 = main, 2 = accelerated, etc.

    def __repr__(self):
        return f"<AuctionEntry: {self.player.name if self.player else '?'} - {self.status.value}>"


class AuctionBid(Base):
    """
    Individual bid in the auction.
    """
    __tablename__ = "auction_bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auctions.id"))
    auction: Mapped["Auction"] = relationship("Auction", back_populates="bids")

    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    bid_amount: Mapped[int] = mapped_column(BigInteger)
    bid_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    is_winning_bid: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        return f"<Bid: {self.bid_amount:,} by team {self.team_id}>"


class TeamAuctionState(Base):
    """
    Tracks a team's state during auction.
    """
    __tablename__ = "team_auction_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auctions.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    # Budget
    remaining_budget: Mapped[int] = mapped_column(BigInteger)

    # Squad composition
    total_players: Mapped[int] = mapped_column(Integer, default=0)
    overseas_players: Mapped[int] = mapped_column(Integer, default=0)
    batsmen: Mapped[int] = mapped_column(Integer, default=0)
    bowlers: Mapped[int] = mapped_column(Integer, default=0)
    all_rounders: Mapped[int] = mapped_column(Integer, default=0)
    wicket_keepers: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def slots_remaining(self) -> int:
        return 25 - self.total_players  # max_squad_size

    @property
    def overseas_slots_remaining(self) -> int:
        return 8 - self.overseas_players  # max_overseas

    @property
    def min_players_needed(self) -> int:
        return max(0, 18 - self.total_players)  # min_squad_size

    @property
    def max_bid_possible(self) -> int:
        """
        Maximum bid this team can make while ensuring they can fill minimum squad.
        Reserve 2 crore per remaining slot needed.
        """
        slots_to_fill = self.min_players_needed - 1  # -1 for current player
        reserved = slots_to_fill * 20000000  # 2 crore each
        return max(0, self.remaining_budget - reserved)

    def __repr__(self):
        return f"<TeamAuctionState: {self.total_players} players, ₹{self.remaining_budget:,} remaining>"
