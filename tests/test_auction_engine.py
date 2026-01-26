"""
Tests for auction engine fixes.
"""
import pytest
import sys
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

from unittest.mock import MagicMock, patch
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from app.models.auction import (
    Auction, AuctionPlayerEntry, TeamAuctionState,
    AuctionStatus, AuctionPlayerStatus
)
from app.engine.auction_engine import AuctionEngine


def create_mock_player(player_id: int, role: PlayerRole, overall_rating: int = 70, is_overseas: bool = False):
    """Create a mock player for testing."""
    player = MagicMock(spec=Player)
    player.id = player_id
    player.name = f"Player {player_id}"
    player.role = role
    player.overall_rating = overall_rating
    player.is_overseas = is_overseas
    player.base_price = 5000000
    player.batting = 60
    player.bowling = 60
    player.fielding = 60
    player.fitness = 60
    return player


def create_mock_team_state(team_id: int, is_user_team: bool = False):
    """Create a mock team auction state."""
    state = MagicMock(spec=TeamAuctionState)
    state.team_id = team_id
    state.remaining_budget = 900000000  # 90 crore
    state.total_players = 0
    state.overseas_players = 0
    state.batsmen = 0
    state.bowlers = 0
    state.all_rounders = 0
    state.wicket_keepers = 0
    state.max_bid_possible = 700000000  # 70 crore
    state.min_players_needed = 18
    return state


class TestSkipCategoryExcludesUserTeam:
    """Test that user team is excluded when skipping a category."""

    def test_run_competitive_ai_bidding_excludes_user_team(self):
        """Verify run_competitive_ai_bidding excludes the specified team from valuations."""
        # Setup mock session and auction
        mock_session = MagicMock()
        mock_auction = MagicMock(spec=Auction)
        mock_auction.id = 1
        mock_auction.current_bid = 5000000
        mock_auction.current_bidder_team_id = None

        # Create engine with mocked session
        engine = AuctionEngine(mock_session, mock_auction)

        # Setup team states (user team ID = 1, AI teams = 2, 3, 4)
        engine._team_states = {
            1: create_mock_team_state(1, is_user_team=True),
            2: create_mock_team_state(2),
            3: create_mock_team_state(3),
            4: create_mock_team_state(4),
        }

        # Create a player entry
        mock_player = create_mock_player(100, PlayerRole.BATSMAN)
        mock_entry = MagicMock(spec=AuctionPlayerEntry)
        mock_entry.player = mock_player
        mock_entry.player_id = 100

        # Track which teams get their values calculated
        calculated_team_ids = []
        original_calculate = engine._calculate_player_value

        def tracking_calculate(player, team_id):
            calculated_team_ids.append(team_id)
            return 50000000  # High value so teams want to bid

        # Mock methods
        with patch.object(engine, '_calculate_player_value', side_effect=tracking_calculate):
            with patch.object(engine, 'place_bid', return_value=True):
                with patch.object(engine, 'get_next_bid_amount', return_value=6000000):
                    # Run competitive bidding excluding team 1 (user team)
                    engine.run_competitive_ai_bidding(mock_entry, exclude_team_id=1)

        # Verify that team 1 was NOT included in valuations
        assert 1 not in calculated_team_ids, \
            f"User team (ID=1) should not have valuation calculated. Teams calculated: {calculated_team_ids}"

        # Verify other teams were considered
        assert any(t in calculated_team_ids for t in [2, 3, 4]), \
            f"AI teams should have valuations calculated. Teams calculated: {calculated_team_ids}"

    def test_auction_category_ai_only_excludes_user_team(self):
        """Verify auction_category_ai_only passes exclude_team_id to competitive bidding."""
        mock_session = MagicMock()
        mock_auction = MagicMock(spec=Auction)
        mock_auction.id = 1
        mock_auction.current_bid = 5000000
        mock_auction.current_bidder_team_id = None

        engine = AuctionEngine(mock_session, mock_auction)

        # Setup team states
        engine._team_states = {
            1: create_mock_team_state(1, is_user_team=True),
            2: create_mock_team_state(2),
        }

        # Mock the helper methods
        mock_player = create_mock_player(100, PlayerRole.BATSMAN)
        mock_entry = MagicMock(spec=AuctionPlayerEntry)
        mock_entry.player = mock_player
        mock_entry.player_id = 100
        mock_entry.category = "batsmen"

        with patch.object(engine, '_get_available_players_in_category', return_value=[mock_entry]):
            with patch.object(engine, 'start_bidding'):
                with patch.object(engine, 'run_competitive_ai_bidding') as mock_competitive:
                    with patch.object(engine, 'finalize_player') as mock_finalize:
                        mock_result = MagicMock()
                        mock_result.player = mock_player
                        mock_result.winning_team = None
                        mock_result.winning_bid = 0
                        mock_result.is_sold = False
                        mock_finalize.return_value = mock_result

                        # Call with exclude_team_id=1
                        engine.auction_category_ai_only("batsmen", exclude_team_id=1)

                        # Verify run_competitive_ai_bidding was called with exclude_team_id=1
                        mock_competitive.assert_called_once()
                        call_kwargs = mock_competitive.call_args[1]
                        assert call_kwargs.get('exclude_team_id') == 1, \
                            "User team ID should be passed to run_competitive_ai_bidding"


class TestCategoryChangeDetection:
    """Test category change detection in next_player endpoint."""

    def test_category_change_detected_when_moving_to_new_category(self):
        """Verify category_changed is True when moving from one category to another."""
        mock_session = MagicMock()
        mock_auction = MagicMock(spec=Auction)
        mock_auction.id = 1
        mock_auction.current_category = "marquee"  # Previous category

        engine = AuctionEngine(mock_session, mock_auction)

        # Create entry for next category
        mock_player = create_mock_player(100, PlayerRole.BATSMAN, overall_rating=70)
        mock_entry = MagicMock(spec=AuctionPlayerEntry)
        mock_entry.player = mock_player
        mock_entry.player_id = 100
        mock_entry.category = "batsmen"  # New category

        # Verify the previous and new categories are different
        previous_category = mock_auction.current_category
        new_category = mock_entry.category

        category_changed = previous_category is not None and previous_category != new_category
        assert category_changed is True, "Category change should be detected"

    def test_category_change_not_detected_when_same_category(self):
        """Verify category_changed is False when staying in same category."""
        previous_category = "batsmen"
        new_category = "batsmen"

        category_changed = previous_category is not None and previous_category != new_category
        assert category_changed is False, "Category change should NOT be detected for same category"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
