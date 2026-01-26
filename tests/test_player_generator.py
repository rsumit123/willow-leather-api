"""
Tests for player generator - verifying all players have 55+ OVR.
"""
import pytest
import sys
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

from app.generators.player_generator import PlayerGenerator
from app.models.player import PlayerRole


class TestPlayerGeneratorMinimumOVR:
    """Test that all generated players have minimum 55 OVR."""

    def test_single_player_has_minimum_ovr(self):
        """Verify a single generated player has 55+ OVR."""
        for tier in ["elite", "star", "good", "solid"]:
            for _ in range(10):  # Test multiple times per tier
                player = PlayerGenerator.generate_player(tier=tier)
                assert player.overall_rating >= 55, \
                    f"Player {player.name} (tier={tier}) has OVR {player.overall_rating} < 55"

    def test_player_pool_all_above_minimum_ovr(self):
        """Verify all players in generated pool have 55+ OVR."""
        players = PlayerGenerator.generate_player_pool()

        min_ovr = min(p.overall_rating for p in players)
        below_55 = [p for p in players if p.overall_rating < 55]

        assert len(below_55) == 0, \
            f"Found {len(below_55)} players below 55 OVR. Minimum OVR: {min_ovr}"

    def test_player_pool_size_is_230(self):
        """Verify player pool has 230 players."""
        players = PlayerGenerator.generate_player_pool()
        assert len(players) == 230, f"Expected 230 players, got {len(players)}"

    def test_role_distribution_is_balanced(self):
        """Verify player pool has reasonable role distribution."""
        players = PlayerGenerator.generate_player_pool()

        role_counts = {role: 0 for role in PlayerRole}
        for player in players:
            role_counts[player.role] += 1

        # Each role should have at least 20 players
        for role, count in role_counts.items():
            assert count >= 20, f"Role {role.value} only has {count} players (expected >= 20)"

    def test_overseas_distribution(self):
        """Verify reasonable overseas player distribution for IPL rules."""
        players = PlayerGenerator.generate_player_pool()

        overseas = sum(1 for p in players if p.is_overseas)
        indian = len(players) - overseas

        # Should have more Indian players than overseas (IPL rules: 4 overseas per XI)
        assert indian > overseas, \
            f"Should have more Indian ({indian}) than overseas ({overseas}) players"

        # For IPL: each team can have max 8 overseas players
        # With 8 teams * 8 = 64 overseas slots, plus some buffer
        # Overseas should be between 10-50% - weighted towards Indian players
        overseas_pct = overseas / len(players) * 100
        assert 10 <= overseas_pct <= 50, \
            f"Overseas percentage {overseas_pct:.1f}% should be between 10-50%"

        # Ensure there are enough overseas players (at least 8 per team = 64)
        assert overseas >= 64, \
            f"Should have at least 64 overseas players (8 per team), got {overseas}"

    def test_ensure_minimum_ovr_function_works(self):
        """Test the _ensure_minimum_ovr helper function directly."""
        from app.models.player import Player, BowlingType, BattingStyle

        # Create a player with low attributes that would result in < 55 OVR
        player = Player(
            name="Low OVR Test",
            age=25,
            nationality="India",
            is_overseas=False,
            role=PlayerRole.BATSMAN,
            batting_style=BattingStyle.RIGHT_HANDED,
            bowling_type=BowlingType.NONE,
            batting=40,  # Low
            bowling=20,
            fielding=40,
            fitness=40,
            power=40,
            technique=40,
            running=40,
            pace_or_spin=20,
            accuracy=20,
            variation=20,
            temperament=40,
            consistency=40,
            form=1.0,
            traits="[]",
            base_price=2000000,
        )

        initial_ovr = player.overall_rating
        assert initial_ovr < 55, f"Test setup error: initial OVR should be < 55, got {initial_ovr}"

        # Apply the minimum OVR fix
        player = PlayerGenerator._ensure_minimum_ovr(player, min_ovr=55)

        assert player.overall_rating >= 55, \
            f"After _ensure_minimum_ovr, OVR should be >= 55, got {player.overall_rating}"

    def test_ovr_distribution_is_reasonable(self):
        """Verify OVR distribution across the player pool."""
        players = PlayerGenerator.generate_player_pool()

        ovrs = [p.overall_rating for p in players]
        avg_ovr = sum(ovrs) / len(ovrs)
        min_ovr = min(ovrs)
        max_ovr = max(ovrs)

        # Minimum should be >= 55
        assert min_ovr >= 55, f"Minimum OVR {min_ovr} should be >= 55"

        # Maximum should be reasonable (around 90-95)
        assert max_ovr <= 100, f"Maximum OVR {max_ovr} should be <= 100"

        # Average should be reasonable (around 65-75)
        assert 60 <= avg_ovr <= 80, \
            f"Average OVR {avg_ovr:.1f} should be between 60-80"

        print(f"\nOVR Distribution:")
        print(f"  Min: {min_ovr}")
        print(f"  Max: {max_ovr}")
        print(f"  Avg: {avg_ovr:.1f}")

        # Count by OVR ranges
        ranges = [(55, 65), (65, 75), (75, 85), (85, 100)]
        for low, high in ranges:
            count = sum(1 for o in ovrs if low <= o < high)
            pct = count / len(ovrs) * 100
            print(f"  {low}-{high}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
