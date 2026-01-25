"""
Auction Engine - Handles IPL-style player auction with AI bidding
"""
import random
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session

from app.models.player import Player, PlayerRole
from app.models.team import Team
from app.models.auction import (
    Auction, AuctionPlayerEntry, AuctionBid, TeamAuctionState,
    AuctionStatus, AuctionPlayerStatus
)


@dataclass
class BidResult:
    """Result of a bidding round"""
    player: Player
    winning_team: Optional[Team]
    winning_bid: int
    is_sold: bool
    bid_history: list[dict]


@dataclass
class TeamNeeds:
    """Analysis of what a team needs"""
    needs_batsmen: int
    needs_bowlers: int
    needs_all_rounders: int
    needs_wicket_keeper: int
    needs_overseas_star: bool
    urgency: float  # 0-1, how urgently they need players


class AuctionEngine:
    """
    Manages the auction process including AI bidding decisions.
    """

    # Bid increments based on current bid
    BID_INCREMENTS = [
        (0, 500000),           # Up to 0: 5 lakh increments
        (10000000, 1000000),   # 1 crore+: 10 lakh increments
        (50000000, 2500000),   # 5 crore+: 25 lakh increments
        (100000000, 5000000),  # 10 crore+: 50 lakh increments
        (150000000, 10000000), # 15 crore+: 1 crore increments
    ]

    def __init__(self, session: Session, auction: Auction):
        self.session = session
        self.auction = auction
        self._team_states: dict[int, TeamAuctionState] = {}
        self._load_team_states()

    def _load_team_states(self):
        """Load or initialize team auction states"""
        states = self.session.query(TeamAuctionState).filter_by(auction_id=self.auction.id).all()
        for state in states:
            self._team_states[state.team_id] = state

    def get_team_state(self, team_id: int) -> TeamAuctionState:
        """Get auction state for a team"""
        return self._team_states.get(team_id)

    def initialize_auction(self, teams: list[Team], players: list[Player]) -> Auction:
        """
        Set up the auction with all teams and players.
        """
        # Create team auction states
        for team in teams:
            state = TeamAuctionState(
                auction_id=self.auction.id,
                team_id=team.id,
                remaining_budget=team.budget,
            )
            self.session.add(state)
            self._team_states[team.id] = state

        # Create player entries with auction order
        # Order: Stars first (by overall rating desc), then by base price
        sorted_players = sorted(
            players,
            key=lambda p: (-p.base_price, -p.overall_rating)
        )

        for order, player in enumerate(sorted_players, 1):
            entry = AuctionPlayerEntry(
                auction_id=self.auction.id,
                player_id=player.id,
                auction_order=order,
                status=AuctionPlayerStatus.AVAILABLE,
            )
            self.session.add(entry)

        self.auction.total_players = len(players)
        self.auction.status = AuctionStatus.IN_PROGRESS
        self.session.commit()

        return self.auction

    def get_next_bid_amount(self, current_bid: int) -> int:
        """Calculate the next bid increment"""
        increment = self.BID_INCREMENTS[0][1]
        for threshold, inc in self.BID_INCREMENTS:
            if current_bid >= threshold:
                increment = inc
        return current_bid + increment

    def get_next_player(self) -> Optional[AuctionPlayerEntry]:
        """Get the next player up for auction"""
        entry = (
            self.session.query(AuctionPlayerEntry)
            .filter_by(auction_id=self.auction.id, status=AuctionPlayerStatus.AVAILABLE)
            .order_by(AuctionPlayerEntry.auction_order)
            .first()
        )
        return entry

    def start_bidding(self, player_entry: AuctionPlayerEntry) -> None:
        """Start bidding on a player"""
        player_entry.status = AuctionPlayerStatus.IN_BIDDING
        self.auction.current_player_id = player_entry.player_id
        self.auction.current_bid = player_entry.player.base_price
        self.auction.current_bidder_team_id = None
        self.session.commit()

    def _analyze_team_needs(self, team_id: int) -> TeamNeeds:
        """Analyze what a team needs"""
        state = self._team_states[team_id]

        # Ideal composition for T20: 4-5 batsmen, 1-2 WK, 2-3 all-rounders, 4-5 bowlers
        ideal_batsmen = 5
        ideal_bowlers = 5
        ideal_ar = 3
        ideal_wk = 2

        needs = TeamNeeds(
            needs_batsmen=max(0, ideal_batsmen - state.batsmen),
            needs_bowlers=max(0, ideal_bowlers - state.bowlers),
            needs_all_rounders=max(0, ideal_ar - state.all_rounders),
            needs_wicket_keeper=max(0, ideal_wk - state.wicket_keepers),
            needs_overseas_star=(state.overseas_players < 4 and state.total_players < 10),
            urgency=min(1.0, state.min_players_needed / 10) if state.min_players_needed > 0 else 0.3,
        )

        return needs

    def _calculate_player_value(self, player: Player, team_id: int) -> int:
        """
        Calculate how much a team should value a player.
        Returns maximum bid amount.
        """
        state = self._team_states[team_id]
        needs = self._analyze_team_needs(team_id)

        # Base value from player rating
        base_value = player.base_price

        # Multiplier based on player quality
        quality_multiplier = 1.0
        if player.overall_rating >= 85:
            quality_multiplier = 3.0  # Star player
        elif player.overall_rating >= 75:
            quality_multiplier = 2.0  # Good player
        elif player.overall_rating >= 65:
            quality_multiplier = 1.5  # Decent player
        elif player.overall_rating >= 55:
            quality_multiplier = 1.2  # Average player
        else:
            quality_multiplier = 0.8  # Below average

        # Adjust based on team needs
        need_multiplier = 1.0
        if player.role == PlayerRole.BATSMAN and needs.needs_batsmen > 2:
            need_multiplier = 1.5
        elif player.role == PlayerRole.BOWLER and needs.needs_bowlers > 2:
            need_multiplier = 1.5
        elif player.role == PlayerRole.ALL_ROUNDER and needs.needs_all_rounders > 1:
            need_multiplier = 1.8  # All-rounders are valuable
        elif player.role == PlayerRole.WICKET_KEEPER and needs.needs_wicket_keeper > 0:
            need_multiplier = 1.6

        # Overseas star bonus
        if player.is_overseas and needs.needs_overseas_star and player.overall_rating >= 75:
            need_multiplier *= 1.3

        # Urgency factor - bid more aggressively if running out of slots
        urgency_multiplier = 1.0 + (needs.urgency * 0.5)

        # Calculate max value
        max_value = int(base_value * quality_multiplier * need_multiplier * urgency_multiplier)

        # Cap at what team can afford
        max_affordable = state.max_bid_possible
        max_value = min(max_value, max_affordable)

        # Add some randomness (±15%)
        variance = random.uniform(0.85, 1.15)
        max_value = int(max_value * variance)

        return max(player.base_price, max_value)

    def _should_team_bid(self, team_id: int, player: Player, current_bid: int) -> bool:
        """Determine if an AI team should place a bid"""
        state = self._team_states[team_id]

        # Can't bid if at max squad size
        if state.total_players >= 25:
            return False

        # Can't bid on overseas if at limit
        if player.is_overseas and state.overseas_players >= 8:
            return False

        # Can't afford
        next_bid = self.get_next_bid_amount(current_bid)
        if next_bid > state.max_bid_possible:
            return False

        # Calculate player value for this team
        max_value = self._calculate_player_value(player, team_id)

        # Bid if current price is below our valuation
        if next_bid <= max_value:
            # Add probability factor based on how close to max value
            price_ratio = next_bid / max_value
            # Higher chance to bid when price is low relative to valuation
            bid_probability = max(0.1, 1.0 - (price_ratio * 0.8))

            # Increase probability if team really needs this type of player
            needs = self._analyze_team_needs(team_id)
            if (
                (player.role == PlayerRole.BATSMAN and needs.needs_batsmen > 2) or
                (player.role == PlayerRole.BOWLER and needs.needs_bowlers > 2) or
                (player.role == PlayerRole.ALL_ROUNDER and needs.needs_all_rounders > 1) or
                (player.role == PlayerRole.WICKET_KEEPER and needs.needs_wicket_keeper > 0)
            ):
                bid_probability = min(1.0, bid_probability + 0.3)

            return random.random() < bid_probability

        return False

    def get_ai_bids(
        self,
        player: Player,
        current_bid: int,
        current_bidder_id: Optional[int],
        include_user_team: bool = False
    ) -> list[int]:
        """
        Get list of AI team IDs that want to bid.
        Returns teams in random order who want to bid.

        Args:
            include_user_team: If True, include user team in AI bidding (for auto-complete)
        """
        interested_teams = []

        for team_id, state in self._team_states.items():
            # Skip if this team is already the current bidder
            if team_id == current_bidder_id:
                continue

            # Skip user team (they bid manually) unless include_user_team is True
            if not include_user_team:
                team = self.session.query(Team).get(team_id)
                if team and team.is_user_team:
                    continue

            if self._should_team_bid(team_id, player, current_bid):
                interested_teams.append(team_id)

        random.shuffle(interested_teams)
        return interested_teams

    def place_bid(self, team_id: int, player_id: int, amount: int) -> bool:
        """Place a bid for a team"""
        state = self._team_states[team_id]

        # Validate bid
        if amount > state.max_bid_possible:
            return False

        if amount <= self.auction.current_bid:
            return False

        # Record bid
        bid = AuctionBid(
            auction_id=self.auction.id,
            player_id=player_id,
            team_id=team_id,
            bid_amount=amount,
        )
        self.session.add(bid)

        # Update auction state
        self.auction.current_bid = amount
        self.auction.current_bidder_team_id = team_id
        self.session.commit()

        return True

    def finalize_player(self, player_entry: AuctionPlayerEntry) -> BidResult:
        """
        Finalize bidding on a player - either sold or unsold.
        """
        player = player_entry.player
        winning_team = None
        is_sold = False

        if self.auction.current_bidder_team_id:
            # Player is sold
            winning_team = self.session.query(Team).get(self.auction.current_bidder_team_id)
            winning_bid = self.auction.current_bid

            # Update player entry
            player_entry.status = AuctionPlayerStatus.SOLD
            player_entry.sold_to_team_id = winning_team.id
            player_entry.sold_price = winning_bid

            # Update player
            player.team_id = winning_team.id
            player.sold_price = winning_bid

            # Update team auction state
            state = self._team_states[winning_team.id]
            state.remaining_budget -= winning_bid
            state.total_players += 1
            if player.is_overseas:
                state.overseas_players += 1
            if player.role == PlayerRole.BATSMAN:
                state.batsmen += 1
            elif player.role == PlayerRole.BOWLER:
                state.bowlers += 1
            elif player.role == PlayerRole.ALL_ROUNDER:
                state.all_rounders += 1
            elif player.role == PlayerRole.WICKET_KEEPER:
                state.wicket_keepers += 1

            # Update team remaining budget
            winning_team.remaining_budget -= winning_bid

            # Mark winning bid
            final_bid = (
                self.session.query(AuctionBid)
                .filter_by(
                    auction_id=self.auction.id,
                    player_id=player.id,
                    team_id=winning_team.id,
                    bid_amount=winning_bid
                )
                .first()
            )
            if final_bid:
                final_bid.is_winning_bid = True

            self.auction.players_sold += 1
            is_sold = True
        else:
            # Player unsold
            player_entry.status = AuctionPlayerStatus.UNSOLD
            self.auction.players_unsold += 1
            winning_bid = 0

        # Clear current bidding state
        self.auction.current_player_id = None
        self.auction.current_bid = 0
        self.auction.current_bidder_team_id = None

        self.session.commit()

        # Get bid history
        bids = (
            self.session.query(AuctionBid)
            .filter_by(auction_id=self.auction.id, player_id=player.id)
            .order_by(AuctionBid.bid_time)
            .all()
        )
        bid_history = [
            {"team_id": b.team_id, "amount": b.bid_amount}
            for b in bids
        ]

        return BidResult(
            player=player,
            winning_team=winning_team,
            winning_bid=winning_bid,
            is_sold=is_sold,
            bid_history=bid_history,
        )

    def run_bidding_round(
        self,
        player_entry: AuctionPlayerEntry,
        user_team_id: int,
        user_bids: bool = False,
        auto_mode: bool = False
    ) -> tuple[int, Optional[int]]:
        """
        Run a single round of bidding.

        Args:
            auto_mode: If True, include user team in AI bidding (for auto-complete)

        Returns: (new_bid_amount, bidding_team_id) or (current_bid, None) if no bids
        """
        player = player_entry.player
        current_bid = self.auction.current_bid
        current_bidder = self.auction.current_bidder_team_id

        # Get AI teams interested in bidding
        ai_bidders = self.get_ai_bids(player, current_bid, current_bidder, include_user_team=auto_mode)

        # If user wants to bid, add them to the pool
        all_bidders = ai_bidders.copy()
        if user_bids and user_team_id != current_bidder:
            state = self._team_states.get(user_team_id)
            next_bid = self.get_next_bid_amount(current_bid)
            if state and next_bid <= state.max_bid_possible:
                # Check overseas limit
                if not player.is_overseas or state.overseas_players < 8:
                    all_bidders.append(user_team_id)
                    random.shuffle(all_bidders)

        if not all_bidders:
            return current_bid, None

        # Pick one bidder (simulating quick auction dynamics)
        bidder_id = all_bidders[0]
        next_bid = self.get_next_bid_amount(current_bid)

        if self.place_bid(bidder_id, player.id, next_bid):
            return next_bid, bidder_id

        return current_bid, None

    def simulate_full_bidding(self, player_entry: AuctionPlayerEntry, user_team_id: int) -> list[dict]:
        """
        Simulate all bidding until sold/unsold (for auto-complete).
        Includes user team in AI bidding.
        Returns list of all bids.
        """
        bids = []
        consecutive_no_bids = 0
        max_rounds = 100  # Safety limit

        for _ in range(max_rounds):
            new_bid, bidder = self.run_bidding_round(player_entry, user_team_id, user_bids=False, auto_mode=True)

            if bidder is None:
                consecutive_no_bids += 1
                if consecutive_no_bids >= 2:  # Two passes = sold to current bidder
                    break
            else:
                consecutive_no_bids = 0
                team = self.session.query(Team).get(bidder)
                bids.append({
                    "team_id": bidder,
                    "team_name": team.short_name if team else "?",
                    "amount": new_bid,
                })

        return bids

    def is_auction_complete(self) -> bool:
        """Check if auction is complete"""
        remaining = (
            self.session.query(AuctionPlayerEntry)
            .filter_by(auction_id=self.auction.id, status=AuctionPlayerStatus.AVAILABLE)
            .count()
        )
        return remaining == 0

    def complete_auction(self) -> None:
        """Mark auction as complete"""
        self.auction.status = AuctionStatus.COMPLETED
        self.session.commit()
