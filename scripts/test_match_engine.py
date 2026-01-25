#!/usr/bin/env python3
"""
Test script to validate match engine produces realistic T20 statistics.
Runs 50+ simulations and compares against real T20 benchmarks.
"""
import sys
import random
import json
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

from app.engine.match_engine import MatchEngine
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from statistics import mean, stdev

# Real T20 benchmarks (IPL averages) - with reasonable variance tolerance
BENCHMARKS = {
    "avg_team_score": (145, 185),      # Typical range with variance
    "avg_wickets": (4, 8),              # Per innings
    "avg_boundaries": (15, 30),         # 4s + 6s per innings
    "wicket_rate_per_ball": (0.03, 0.06),  # 3-6% (slightly wider)
}


def create_player(player_id: int, name: str, role: PlayerRole, batting: int, bowling: int, power: int = 50) -> Player:
    """Create a player without database"""
    player = Player(
        name=name,
        age=25,
        nationality="India",
        is_overseas=False,
        role=role,
        batting_style=BattingStyle.RIGHT_HANDED,
        bowling_type=BowlingType.PACE if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER] else BowlingType.NONE,
        batting=batting,
        bowling=bowling,
        fielding=60,
        fitness=70,
        power=power,
        technique=60,
        running=60,
        pace_or_spin=60,
        accuracy=60,
        variation=50,
        temperament=60,
        consistency=60,
        form=1.0,
        traits=json.dumps([]),
        base_price=5000000,
    )
    player.id = player_id
    return player


def generate_test_team(start_id: int, tier_mix: dict = None) -> list:
    """Generate a test team with realistic IPL-like stats - balanced teams"""
    players = []
    player_id = start_id

    # Balanced player templates - tighter ranges for more consistent results
    # All teams have similar overall strength
    player_templates = [
        # Openers (2) - good batting, 72-77 avg
        {"role": PlayerRole.BATSMAN, "batting": (72, 78), "bowling": (22, 28), "power": (68, 76)},
        {"role": PlayerRole.BATSMAN, "batting": (70, 76), "bowling": (22, 28), "power": (65, 73)},
        # Middle order (3) - WK and batsmen, 65-72 avg
        {"role": PlayerRole.WICKET_KEEPER, "batting": (65, 72), "bowling": (18, 24), "power": (58, 66)},
        {"role": PlayerRole.BATSMAN, "batting": (66, 73), "bowling": (22, 28), "power": (62, 70)},
        {"role": PlayerRole.BATSMAN, "batting": (62, 69), "bowling": (22, 28), "power": (58, 66)},
        # All-rounders (2) - balanced, 60-67 in both
        {"role": PlayerRole.ALL_ROUNDER, "batting": (60, 67), "bowling": (60, 67), "power": (54, 62)},
        {"role": PlayerRole.ALL_ROUNDER, "batting": (58, 65), "bowling": (62, 69), "power": (52, 60)},
        # Bowlers (4) - good bowling, 65-73 avg
        {"role": PlayerRole.BOWLER, "batting": (28, 36), "bowling": (70, 76), "power": (32, 42)},
        {"role": PlayerRole.BOWLER, "batting": (28, 36), "bowling": (68, 74), "power": (32, 42)},
        {"role": PlayerRole.BOWLER, "batting": (25, 33), "bowling": (66, 72), "power": (28, 38)},
        {"role": PlayerRole.BOWLER, "batting": (25, 33), "bowling": (64, 70), "power": (28, 38)},
    ]

    for template in player_templates:
        batting = random.randint(*template["batting"])
        bowling = random.randint(*template["bowling"])
        power = random.randint(*template["power"])

        player = create_player(
            player_id=player_id,
            name=f"Player {player_id}",
            role=template["role"],
            batting=batting,
            bowling=bowling,
            power=power
        )
        players.append(player)
        player_id += 1

    return players


def run_simulations(num_matches: int = 50):
    """Run match simulations and validate results"""
    results = {
        "team1_scores": [],
        "team1_wickets": [],
        "team2_scores": [],
        "team2_wickets": [],
        "total_boundaries": [],
    }

    print(f"Running {num_matches} match simulations...\n")

    for i in range(num_matches):
        engine = MatchEngine()

        team1 = generate_test_team(start_id=1)
        team2 = generate_test_team(start_id=100)

        result = engine.simulate_match(team1, team2)

        results["team1_scores"].append(result["innings1"]["runs"])
        results["team1_wickets"].append(result["innings1"]["wickets"])
        results["team2_scores"].append(result["innings2"]["runs"])
        results["team2_wickets"].append(result["innings2"]["wickets"])

        # Count boundaries from innings data
        boundaries = 0
        for innings in [engine.innings1, engine.innings2]:
            for bi in innings.batter_innings.values():
                boundaries += bi.fours + bi.sixes
        results["total_boundaries"].append(boundaries)

        print(f"Match {i+1}: {result['innings1']['runs']}/{result['innings1']['wickets']} vs {result['innings2']['runs']}/{result['innings2']['wickets']} - Winner: {result['winner']} by {result['margin']}")

    # Calculate statistics
    all_scores = results["team1_scores"] + results["team2_scores"]
    all_wickets = results["team1_wickets"] + results["team2_wickets"]

    print("\n" + "="*60)
    print("SIMULATION RESULTS")
    print("="*60)
    print(f"Matches simulated: {num_matches}")
    print(f"Average score: {mean(all_scores):.1f} (benchmark: {BENCHMARKS['avg_team_score']})")
    print(f"Score std dev: {stdev(all_scores):.1f}")
    print(f"Min score: {min(all_scores)}, Max score: {max(all_scores)}")
    print(f"Average wickets: {mean(all_wickets):.1f} (benchmark: {BENCHMARKS['avg_wickets']})")
    print(f"Average boundaries (both innings): {mean(results['total_boundaries']):.1f} (benchmark: {BENCHMARKS['avg_boundaries']})")

    wicket_rate = mean(all_wickets) / 120  # 120 balls per innings
    print(f"Wicket rate per ball: {wicket_rate:.4f} (benchmark: {BENCHMARKS['wicket_rate_per_ball']})")

    # Validation
    print("\n" + "="*60)
    print("VALIDATION")
    print("="*60)

    checks = [
        ("Average score in range", BENCHMARKS['avg_team_score'][0] <= mean(all_scores) <= BENCHMARKS['avg_team_score'][1]),
        ("Average wickets in range", BENCHMARKS['avg_wickets'][0] <= mean(all_wickets) <= BENCHMARKS['avg_wickets'][1]),
        ("Wicket rate realistic", BENCHMARKS['wicket_rate_per_ball'][0] <= wicket_rate <= BENCHMARKS['wicket_rate_per_ball'][1]),
    ]

    all_passed = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[X]"
        print(f"{symbol} {status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("All validation checks PASSED!")
    else:
        print("Some validation checks FAILED - adjustments may be needed")
    print("="*60)

    return all_passed


def test_aggression_modes(num_balls: int = 500):
    """Test that different aggression modes produce different outcomes"""
    print("\n" + "="*60)
    print("AGGRESSION MODE TESTING")
    print("="*60)

    # Create test players - need at least 2 batters for setup_innings
    batter = create_player(1, "Test Batter", PlayerRole.BATSMAN, batting=75, bowling=25, power=70)
    batter2 = create_player(2, "Test Batter 2", PlayerRole.BATSMAN, batting=70, bowling=25, power=65)
    bowler = create_player(3, "Test Bowler", PlayerRole.BOWLER, batting=30, bowling=72, power=35)

    from app.engine.match_engine import BatterState, BowlerState

    modes = ["defend", "balanced", "attack"]
    mode_results = {}

    for mode in modes:
        runs = []
        wickets = 0
        boundaries = 0

        for _ in range(num_balls):
            engine = MatchEngine()
            # Create a fresh innings state for each ball
            innings = engine.setup_innings([batter, batter2], [bowler])

            # Reset batter state to neutral for fair comparison
            innings.batter_states[batter.id] = BatterState(player_id=batter.id)
            innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)

            outcome = engine.calculate_ball_outcome(batter, bowler, mode, innings)

            runs.append(outcome.runs)
            if outcome.is_wicket:
                wickets += 1
            if outcome.is_boundary:
                boundaries += 1

        avg_runs = mean(runs)
        wicket_rate = wickets / num_balls * 100
        boundary_rate = boundaries / num_balls * 100

        mode_results[mode] = {
            "avg_runs": avg_runs,
            "wicket_rate": wicket_rate,
            "boundary_rate": boundary_rate,
            "total_runs": sum(runs)
        }

        print(f"\n{mode.upper()} mode ({num_balls} balls):")
        print(f"  Average runs/ball: {avg_runs:.3f}")
        print(f"  Wicket rate: {wicket_rate:.2f}%")
        print(f"  Boundary rate: {boundary_rate:.2f}%")
        print(f"  Total runs: {sum(runs)}")

    # Validation: Check that modes produce different results as expected
    print("\n" + "-"*40)
    print("AGGRESSION MODE VALIDATION")
    print("-"*40)

    checks = []

    # Attack should score more runs than defend
    attack_more_runs = mode_results["attack"]["avg_runs"] > mode_results["defend"]["avg_runs"]
    checks.append(("Attack scores more runs than Defend", attack_more_runs))

    # Attack should have higher boundary rate than defend
    attack_more_boundaries = mode_results["attack"]["boundary_rate"] > mode_results["defend"]["boundary_rate"]
    checks.append(("Attack has more boundaries than Defend", attack_more_boundaries))

    # Attack should have higher wicket rate than defend (more risk)
    attack_more_wickets = mode_results["attack"]["wicket_rate"] > mode_results["defend"]["wicket_rate"]
    checks.append(("Attack has higher wicket risk than Defend", attack_more_wickets))

    # Balanced should be between attack and defend for runs
    balanced_middle = mode_results["defend"]["avg_runs"] <= mode_results["balanced"]["avg_runs"] <= mode_results["attack"]["avg_runs"]
    checks.append(("Balanced is between Defend and Attack for runs", balanced_middle))

    all_passed = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[X]"
        print(f"{symbol} {status}: {name}")
        if not passed:
            all_passed = False

    return all_passed


if __name__ == "__main__":
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    # Run standard simulations
    success1 = run_simulations(num)

    # Run aggression mode tests
    success2 = test_aggression_modes(500)

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(f"Match simulations: {'PASSED' if success1 else 'FAILED'}")
    print(f"Aggression modes: {'PASSED' if success2 else 'FAILED'}")

    sys.exit(0 if (success1 and success2) else 1)
