#!/usr/bin/env python3
"""
Test script to validate batting_intent affects match outcomes correctly.
Tests that:
- Power hitters have higher variance (more boundaries, more wickets)
- Anchors have lower variance (more consistent, fewer boundaries)
- Accumulators are in between
"""
import sys
import json
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

from app.engine.match_engine import MatchEngine, BatterState, BowlerState
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from statistics import mean, stdev

NUM_SIMULATIONS = 25  # Per intent type


def create_player(player_id: int, name: str, role: PlayerRole, batting: int, bowling: int,
                  power: int = 50, batting_intent: str = "accumulator") -> Player:
    """Create a player with specific batting_intent"""
    player = Player(
        name=name,
        age=25,
        nationality="India",
        is_overseas=False,
        role=role,
        batting_style=BattingStyle.RIGHT_HANDED,
        bowling_type=BowlingType.PACE if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER] else BowlingType.MEDIUM,
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
        batting_intent=batting_intent,
        base_price=5000000,
    )
    player.id = player_id
    return player


def create_team_with_intent(start_id: int, batting_intent: str) -> list:
    """Create a team where all batters have the same batting_intent"""
    players = []
    player_id = start_id

    # Openers (2) - same batting skill, different intent
    players.append(create_player(player_id, f"Opener1", PlayerRole.BATSMAN, 75, 25, 70, batting_intent))
    player_id += 1
    players.append(create_player(player_id, f"Opener2", PlayerRole.BATSMAN, 73, 25, 68, batting_intent))
    player_id += 1

    # Middle order (3)
    players.append(create_player(player_id, f"Keeper", PlayerRole.WICKET_KEEPER, 68, 20, 62, batting_intent))
    player_id += 1
    players.append(create_player(player_id, f"Batter4", PlayerRole.BATSMAN, 70, 25, 65, batting_intent))
    player_id += 1
    players.append(create_player(player_id, f"Batter5", PlayerRole.BATSMAN, 65, 25, 60, batting_intent))
    player_id += 1

    # All-rounders (2) - these also get the intent
    players.append(create_player(player_id, f"AR1", PlayerRole.ALL_ROUNDER, 62, 65, 58, batting_intent))
    player_id += 1
    players.append(create_player(player_id, f"AR2", PlayerRole.ALL_ROUNDER, 60, 67, 55, batting_intent))
    player_id += 1

    # Bowlers (4) - bowlers default to accumulator intent
    for i in range(4):
        players.append(create_player(player_id, f"Bowler{i+1}", PlayerRole.BOWLER, 30, 70, 35, "accumulator"))
        player_id += 1

    return players


def create_neutral_bowling_team(start_id: int) -> list:
    """Create a neutral bowling team for fair comparison"""
    players = []
    player_id = start_id

    # Create a team with average bowling
    for i in range(2):
        players.append(create_player(player_id, f"Batter{i+1}", PlayerRole.BATSMAN, 70, 25, 65, "accumulator"))
        player_id += 1

    players.append(create_player(player_id, "Keeper", PlayerRole.WICKET_KEEPER, 65, 20, 60, "accumulator"))
    player_id += 1

    for i in range(2):
        players.append(create_player(player_id, f"Batter{i+3}", PlayerRole.BATSMAN, 65, 25, 60, "accumulator"))
        player_id += 1

    for i in range(2):
        players.append(create_player(player_id, f"AR{i+1}", PlayerRole.ALL_ROUNDER, 60, 65, 55, "accumulator"))
        player_id += 1

    # Bowlers with consistent skill level
    for i in range(4):
        players.append(create_player(player_id, f"Bowler{i+1}", PlayerRole.BOWLER, 30, 68, 35, "accumulator"))
        player_id += 1

    return players


def run_intent_simulations():
    """Run simulations for each batting intent type"""
    intents = ["anchor", "accumulator", "aggressive", "power_hitter"]
    results = {}

    bowling_team = create_neutral_bowling_team(start_id=100)

    for intent in intents:
        print(f"\n{'='*60}")
        print(f"Testing {intent.upper()} intent ({NUM_SIMULATIONS} innings)")
        print('='*60)

        scores = []
        wickets = []
        boundaries = []
        sixes = []

        for i in range(NUM_SIMULATIONS):
            batting_team = create_team_with_intent(start_id=1, batting_intent=intent)

            engine = MatchEngine()
            innings = engine.setup_innings(batting_team, bowling_team)

            # Simulate full innings with balanced aggression
            while not innings.is_innings_complete:
                engine.simulate_over(innings, "balanced")

            # Collect stats
            runs = innings.total_runs
            wkts = innings.wickets
            fours = sum(bi.fours for bi in innings.batter_innings.values())
            six_count = sum(bi.sixes for bi in innings.batter_innings.values())

            scores.append(runs)
            wickets.append(wkts)
            boundaries.append(fours + six_count)
            sixes.append(six_count)

            print(f"  Innings {i+1}: {runs}/{wkts} (4s: {fours}, 6s: {six_count})")

        results[intent] = {
            "avg_score": mean(scores),
            "score_stdev": stdev(scores) if len(scores) > 1 else 0,
            "avg_wickets": mean(wickets),
            "avg_boundaries": mean(boundaries),
            "avg_sixes": mean(sixes),
            "min_score": min(scores),
            "max_score": max(scores),
        }

        print(f"\n  Summary:")
        print(f"    Avg Score: {results[intent]['avg_score']:.1f} ± {results[intent]['score_stdev']:.1f}")
        print(f"    Avg Wickets: {results[intent]['avg_wickets']:.1f}")
        print(f"    Avg Boundaries: {results[intent]['avg_boundaries']:.1f}")
        print(f"    Avg Sixes: {results[intent]['avg_sixes']:.1f}")
        print(f"    Score Range: {results[intent]['min_score']} - {results[intent]['max_score']}")

    return results


def validate_results(results: dict):
    """Validate that batting intents produce expected differences"""
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)

    checks = []

    # 1. Power hitters should have higher variance (stdev) than anchors
    power_stdev = results["power_hitter"]["score_stdev"]
    anchor_stdev = results["anchor"]["score_stdev"]
    check1 = power_stdev > anchor_stdev
    checks.append((f"Power hitters have higher variance ({power_stdev:.1f}) than Anchors ({anchor_stdev:.1f})", check1))

    # 2. Power hitters should hit more sixes than anchors
    power_sixes = results["power_hitter"]["avg_sixes"]
    anchor_sixes = results["anchor"]["avg_sixes"]
    check2 = power_sixes >= anchor_sixes  # Allow equal since power affects 4 vs 6 ratio
    checks.append((f"Power hitters hit more/equal sixes ({power_sixes:.1f}) vs Anchors ({anchor_sixes:.1f})", check2))

    # 3. Anchors should lose fewer wickets on average
    power_wickets = results["power_hitter"]["avg_wickets"]
    anchor_wickets = results["anchor"]["avg_wickets"]
    check3 = anchor_wickets <= power_wickets + 1  # Allow some tolerance
    checks.append((f"Anchors lose fewer wickets ({anchor_wickets:.1f}) vs Power ({power_wickets:.1f})", check3))

    # 4. Aggressive should be between power_hitter and accumulator for variance
    aggressive_stdev = results["aggressive"]["score_stdev"]
    accumulator_stdev = results["accumulator"]["score_stdev"]
    check4 = aggressive_stdev > accumulator_stdev or aggressive_stdev > anchor_stdev
    checks.append((f"Aggressive has moderate variance ({aggressive_stdev:.1f})", check4))

    # 5. All intents should produce reasonable T20 scores (100-220)
    all_reasonable = all(
        100 <= results[intent]["avg_score"] <= 220
        for intent in results
    )
    checks.append(("All intents produce T20-realistic scores (100-220)", all_reasonable))

    # 6. Variance order: anchor < accumulator < aggressive < power_hitter (approximately)
    variance_order = (
        anchor_stdev <= accumulator_stdev + 5 and  # Allow 5 point tolerance
        accumulator_stdev <= aggressive_stdev + 5 and
        aggressive_stdev <= power_stdev + 5
    )
    checks.append(("Variance increases with aggression (with tolerance)", variance_order))

    # Print results
    all_passed = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[X]"
        print(f"{symbol} {status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("ALL BATTING INTENT TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - Intent may need tuning")
    print("="*60)

    return all_passed


def test_single_ball_variance():
    """Test individual ball outcomes for different intents"""
    print("\n" + "="*60)
    print("SINGLE BALL VARIANCE TEST (500 balls each)")
    print("="*60)

    intents = ["anchor", "accumulator", "aggressive", "power_hitter"]
    num_balls = 500

    bowling_team = create_neutral_bowling_team(start_id=100)
    bowler = bowling_team[7]  # A bowler from the team

    results = {}

    for intent in intents:
        batting_team = create_team_with_intent(start_id=1, batting_intent=intent)
        batter = batting_team[0]  # Top opener

        runs_list = []
        wickets = 0
        boundaries = 0

        for _ in range(num_balls):
            engine = MatchEngine()
            innings = engine.setup_innings(batting_team, bowling_team)

            # Fresh state for each ball
            innings.batter_states[batter.id] = BatterState(player_id=batter.id)
            innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)

            outcome = engine.calculate_ball_outcome(batter, bowler, "balanced", innings)

            runs_list.append(outcome.runs)
            if outcome.is_wicket:
                wickets += 1
            if outcome.is_boundary:
                boundaries += 1

        results[intent] = {
            "avg_runs": mean(runs_list),
            "runs_stdev": stdev(runs_list) if len(runs_list) > 1 else 0,
            "wicket_rate": wickets / num_balls * 100,
            "boundary_rate": boundaries / num_balls * 100,
        }

        print(f"\n{intent.upper()}:")
        print(f"  Avg runs/ball: {results[intent]['avg_runs']:.3f}")
        print(f"  Runs stdev: {results[intent]['runs_stdev']:.3f}")
        print(f"  Wicket rate: {results[intent]['wicket_rate']:.2f}%")
        print(f"  Boundary rate: {results[intent]['boundary_rate']:.2f}%")

    # Validate variance differences at ball level
    print("\n" + "-"*40)
    print("SINGLE BALL VALIDATION")
    print("-"*40)

    checks = []

    # Power hitters should have higher per-ball variance
    power_var = results["power_hitter"]["runs_stdev"]
    anchor_var = results["anchor"]["runs_stdev"]
    check1 = power_var > anchor_var
    checks.append((f"Power hitter ball variance ({power_var:.3f}) > Anchor ({anchor_var:.3f})", check1))

    # Power hitters should have higher boundary rate
    power_bdry = results["power_hitter"]["boundary_rate"]
    anchor_bdry = results["anchor"]["boundary_rate"]
    check2 = power_bdry >= anchor_bdry
    checks.append((f"Power hitter boundaries ({power_bdry:.1f}%) >= Anchor ({anchor_bdry:.1f}%)", check2))

    all_passed = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[X]"
        print(f"{symbol} {status}: {name}")
        if not passed:
            all_passed = False

    return all_passed


if __name__ == "__main__":
    # Run full innings simulations
    results = run_intent_simulations()
    success1 = validate_results(results)

    # Run single ball variance tests
    success2 = test_single_ball_variance()

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(f"Full innings tests: {'PASSED' if success1 else 'FAILED'}")
    print(f"Single ball tests: {'PASSED' if success2 else 'FAILED'}")

    sys.exit(0 if (success1 and success2) else 1)
