"""
Integration tests for auction engine fixes.
Tests the full flow of skipping categories and category changes.
"""
import sys
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from app.models.team import Team
from app.models.auction import (
    Auction, AuctionPlayerEntry, TeamAuctionState,
    AuctionStatus, AuctionPlayerStatus, AuctionCategory
)
from app.engine.auction_engine import AuctionEngine
from app.generators.player_generator import PlayerGenerator


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def teams(test_db):
    """Create test teams."""
    team_data = [
        {"name": "User Team", "short_name": "USR", "is_user_team": True},
        {"name": "AI Team 1", "short_name": "AI1", "is_user_team": False},
        {"name": "AI Team 2", "short_name": "AI2", "is_user_team": False},
        {"name": "AI Team 3", "short_name": "AI3", "is_user_team": False},
    ]
    teams = []
    for data in team_data:
        team = Team(
            name=data["name"],
            short_name=data["short_name"],
            city="Test City",
            home_ground="Test Stadium",
            primary_color="#000000",
            secondary_color="#FFFFFF",
            budget=900000000,  # 90 crore
            remaining_budget=900000000,
            is_user_team=data["is_user_team"],
        )
        test_db.add(team)
        teams.append(team)
    test_db.commit()
    return teams


@pytest.fixture
def players(test_db):
    """Create test players."""
    players = []
    for i in range(20):
        player = Player(
            name=f"Player {i}",
            age=25,
            nationality="India",
            is_overseas=i % 4 == 0,  # 25% overseas
            role=PlayerRole.BATSMAN if i < 10 else PlayerRole.BOWLER,
            batting_style=BattingStyle.RIGHT_HANDED,
            bowling_type=BowlingType.NONE if i < 10 else BowlingType.PACE,
            batting=70 if i < 10 else 30,
            bowling=30 if i < 10 else 70,
            fielding=60,
            fitness=60,
            power=60,
            technique=60,
            running=60,
            pace_or_spin=60,
            accuracy=60,
            variation=50,
            temperament=60,
            consistency=60,
            form=1.0,
            traits="[]",
            base_price=5000000,
        )
        test_db.add(player)
        players.append(player)
    test_db.commit()
    return players


@pytest.fixture
def auction(test_db, teams, players):
    """Create and initialize an auction."""
    auction = Auction(
        season_id=1,  # Fake season ID
        status=AuctionStatus.NOT_STARTED,
        total_players=len(players),
    )
    test_db.add(auction)
    test_db.commit()

    engine = AuctionEngine(test_db, auction)
    engine.initialize_auction(teams, players)

    return auction


class TestSkipCategoryIntegration:
    """Integration tests for skip category functionality."""

    def test_skip_category_excludes_user_team_from_purchases(self, test_db, teams, players, auction):
        """Verify that when user skips a category, no players are assigned to user's team."""
        engine = AuctionEngine(test_db, auction)

        # Get user team
        user_team = next(t for t in teams if t.is_user_team)

        # Count initial players for user team
        initial_user_players = test_db.query(Player).filter_by(team_id=user_team.id).count()
        assert initial_user_players == 0, "User should start with no players"

        # Skip the batsmen category (user team should be excluded)
        results = engine.auction_category_ai_only("batsmen", exclude_team_id=user_team.id)

        # Count players after skipping
        user_players_after = test_db.query(Player).filter_by(team_id=user_team.id).count()

        # Verify NO players were assigned to user team
        assert user_players_after == 0, \
            f"User team should have 0 players after skip, but has {user_players_after}"

        # Verify some players were sold to AI teams
        sold_to_ai = sum(1 for r in results if r["is_sold"] and r["sold_to_team_id"] != user_team.id)
        assert sold_to_ai > 0, "At least some players should be sold to AI teams"

        print(f"\nSkip category test results:")
        print(f"  Players auctioned: {len(results)}")
        print(f"  Players sold to AI: {sold_to_ai}")
        print(f"  Players unsold: {sum(1 for r in results if not r['is_sold'])}")
        print(f"  User team players: {user_players_after}")


class TestCategoryChangeIntegration:
    """Integration tests for category change detection."""

    def test_auction_tracks_current_category(self, test_db, teams, players, auction):
        """Verify auction correctly tracks and changes categories."""
        engine = AuctionEngine(test_db, auction)

        # Get first player (should be marquee or batsmen depending on OVR)
        first_entry = engine.get_next_player()
        assert first_entry is not None, "Should have players to auction"

        # Start bidding
        engine.start_bidding(first_entry)

        # Verify category is set
        assert auction.current_category is not None, "Category should be set"
        first_category = auction.current_category

        print(f"\nCategory tracking test:")
        print(f"  First player category: {first_category}")

        # Finish all players in first category
        engine.finalize_player(first_entry)

        # Keep getting next players and track category changes
        categories_seen = [first_category]
        for _ in range(19):  # Max iterations
            entry = engine.get_next_player()
            if entry is None:
                break
            engine.start_bidding(entry)
            if auction.current_category not in categories_seen:
                categories_seen.append(auction.current_category)
                print(f"  Category changed to: {auction.current_category}")
            engine.finalize_player(entry)

        print(f"  Total categories seen: {len(categories_seen)}")


class TestPlayerGenerationIntegration:
    """Integration tests for player generation."""

    def test_generated_pool_suitable_for_auction(self):
        """Verify generated player pool is suitable for an 8-team auction."""
        players = PlayerGenerator.generate_player_pool()

        # Basic counts
        total = len(players)
        indian = sum(1 for p in players if not p.is_overseas)
        overseas = sum(1 for p in players if p.is_overseas)

        print(f"\nGenerated player pool stats:")
        print(f"  Total players: {total}")
        print(f"  Indian players: {indian}")
        print(f"  Overseas players: {overseas}")

        # Verify counts
        assert total == 230, f"Expected 230 players, got {total}"
        assert overseas >= 64, f"Need at least 64 overseas (8 per team), got {overseas}"
        assert indian >= 144, f"Need at least 144 Indian (18 per team), got {indian}"

        # Verify OVR distribution
        ovrs = [p.overall_rating for p in players]
        min_ovr = min(ovrs)
        max_ovr = max(ovrs)
        avg_ovr = sum(ovrs) / len(ovrs)

        print(f"  Min OVR: {min_ovr}")
        print(f"  Max OVR: {max_ovr}")
        print(f"  Avg OVR: {avg_ovr:.1f}")

        assert min_ovr >= 55, f"Minimum OVR should be >= 55, got {min_ovr}"

        # Verify role distribution for each team's needs
        role_counts = {}
        for p in players:
            role_counts[p.role] = role_counts.get(p.role, 0) + 1

        print(f"  Role distribution:")
        for role, count in role_counts.items():
            print(f"    {role.value}: {count}")

        # Each team needs at least 2 of each role type
        min_per_role = 8 * 2  # 8 teams * 2 players minimum
        for role in PlayerRole:
            assert role_counts.get(role, 0) >= min_per_role, \
                f"Need at least {min_per_role} {role.value}, got {role_counts.get(role, 0)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
