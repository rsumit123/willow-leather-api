#!/usr/bin/env python3
"""
Diagnostic script to thoroughly test the match engine.
Tests individual ball outcomes, simulate_over, and full match scenarios.
"""
import sys
import random
import json
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

from app.engine.match_engine import MatchEngine, BatterState, BowlerState, MatchContext
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from statistics import mean, stdev
from collections import Counter


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


def generate_test_team(start_id: int) -> list:
    """Generate a realistic test team"""
    players = []
    player_id = start_id

    templates = [
        {"role": PlayerRole.BATSMAN, "batting": 75, "bowling": 25, "power": 70},
        {"role": PlayerRole.BATSMAN, "batting": 72, "bowling": 25, "power": 68},
        {"role": PlayerRole.WICKET_KEEPER, "batting": 68, "bowling": 20, "power": 62},
        {"role": PlayerRole.BATSMAN, "batting": 70, "bowling": 25, "power": 65},
        {"role": PlayerRole.BATSMAN, "batting": 65, "bowling": 25, "power": 60},
        {"role": PlayerRole.ALL_ROUNDER, "batting": 62, "bowling": 65, "power": 58},
        {"role": PlayerRole.ALL_ROUNDER, "batting": 58, "bowling": 68, "power": 55},
        {"role": PlayerRole.BOWLER, "batting": 30, "bowling": 72, "power": 35},
        {"role": PlayerRole.BOWLER, "batting": 28, "bowling": 70, "power": 32},
        {"role": PlayerRole.BOWLER, "batting": 25, "bowling": 68, "power": 30},
        {"role": PlayerRole.BOWLER, "batting": 25, "bowling": 66, "power": 30},
    ]

    for template in templates:
        player = create_player(
            player_id=player_id,
            name=f"Player {player_id}",
            role=template["role"],
            batting=template["batting"],
            bowling=template["bowling"],
            power=template["power"]
        )
        players.append(player)
        player_id += 1

    return players


def test_single_ball_outcomes(num_balls: int = 1000):
    """Test individual ball outcomes for each aggression mode"""
    print("\n" + "="*70)
    print("TEST 1: SINGLE BALL OUTCOMES (No state effects)")
    print("="*70)

    batter = create_player(1, "Test Batter", PlayerRole.BATSMAN, batting=70, bowling=25, power=65)
    batter2 = create_player(2, "Non-Striker", PlayerRole.BATSMAN, batting=68, bowling=25, power=62)
    bowler = create_player(3, "Test Bowler", PlayerRole.BOWLER, batting=30, bowling=70, power=35)

    for mode in ["defend", "balanced", "attack"]:
        runs_list = []
        wickets = 0
        boundaries = 0

        for _ in range(num_balls):
            engine = MatchEngine()
            innings = engine.setup_innings([batter, batter2], [bowler])
            # Reset to neutral state (no bonuses)
            innings.batter_states[batter.id] = BatterState(player_id=batter.id)
            innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)
            innings.context.pitch_type = "flat_deck"  # Neutral pitch

            outcome = engine.calculate_ball_outcome(batter, bowler, mode, innings)
            runs_list.append(outcome.runs)
            if outcome.is_wicket:
                wickets += 1
            if outcome.is_boundary:
                boundaries += 1

        avg_runs = mean(runs_list)
        wicket_rate = wickets / num_balls * 100
        boundary_rate = boundaries / num_balls * 100

        print(f"\n{mode.upper()} mode ({num_balls} balls, neutral conditions):")
        print(f"  Average runs/ball: {avg_runs:.3f}")
        print(f"  Wicket rate: {wicket_rate:.2f}%")
        print(f"  Boundary rate: {boundary_rate:.2f}%")
        print(f"  Run distribution: {Counter(runs_list).most_common()}")


def test_with_state_effects(num_balls: int = 500):
    """Test ball outcomes with various state effects"""
    print("\n" + "="*70)
    print("TEST 2: BALL OUTCOMES WITH STATE EFFECTS")
    print("="*70)

    batter = create_player(1, "Test Batter", PlayerRole.BATSMAN, batting=70, bowling=25, power=65)
    batter2 = create_player(2, "Non-Striker", PlayerRole.BATSMAN, batting=68, bowling=25, power=62)
    bowler = create_player(3, "Test Bowler", PlayerRole.BOWLER, batting=30, bowling=70, power=35)

    scenarios = [
        {"name": "Neutral (flat deck)", "pitch": "flat_deck", "nervous": False, "settled": False, "confidence": False},
        {"name": "Green top pitch", "pitch": "green_top", "nervous": False, "settled": False, "confidence": False},
        {"name": "Nervous batter", "pitch": "flat_deck", "nervous": True, "settled": False, "confidence": False},
        {"name": "Settled batter", "pitch": "flat_deck", "nervous": False, "settled": True, "confidence": False},
        {"name": "Confident bowler", "pitch": "flat_deck", "nervous": False, "settled": False, "confidence": True},
        {"name": "WORST CASE (green + nervous + confident)", "pitch": "green_top", "nervous": True, "settled": False, "confidence": True},
    ]

    for scenario in scenarios:
        wickets = 0
        runs_list = []

        for _ in range(num_balls):
            engine = MatchEngine()
            innings = engine.setup_innings([batter, batter2], [bowler])

            # Set up state
            innings.context.pitch_type = scenario["pitch"]
            innings.batter_states[batter.id] = BatterState(
                player_id=batter.id,
                is_nervous=scenario["nervous"],
                is_settled=scenario["settled"],
                balls_faced=20 if scenario["settled"] else 0
            )
            innings.bowler_states[bowler.id] = BowlerState(
                player_id=bowler.id,
                has_confidence=scenario["confidence"]
            )

            outcome = engine.calculate_ball_outcome(batter, bowler, "balanced", innings)
            runs_list.append(outcome.runs)
            if outcome.is_wicket:
                wickets += 1

        wicket_rate = wickets / num_balls * 100
        avg_runs = mean(runs_list)
        print(f"\n{scenario['name']}:")
        print(f"  Wicket rate: {wicket_rate:.2f}%, Avg runs: {avg_runs:.3f}")


def test_simulate_over():
    """Test simulate_over function"""
    print("\n" + "="*70)
    print("TEST 3: SIMULATE OVER (6 balls sequentially)")
    print("="*70)

    team1 = generate_test_team(1)
    team2 = generate_test_team(100)

    num_overs = 100
    over_runs = []
    over_wickets = []
    balls_per_over = []

    for i in range(num_overs):
        engine = MatchEngine()
        innings = engine.setup_innings(team1, team2)
        innings.context.pitch_type = "flat_deck"

        # Initialize batter states for openers
        innings.batter_states[innings.striker_id] = BatterState(player_id=innings.striker_id)
        innings.batter_states[innings.non_striker_id] = BatterState(player_id=innings.non_striker_id)

        outcomes = engine.simulate_over(innings)

        runs = sum(o.runs for o in outcomes)
        wickets = sum(1 for o in outcomes if o.is_wicket)
        balls = len([o for o in outcomes if not o.is_wide and not o.is_no_ball])

        over_runs.append(runs)
        over_wickets.append(wickets)
        balls_per_over.append(balls)

        if i < 5:
            print(f"\nOver {i+1}: {runs} runs, {wickets} wickets")
            print(f"  Ball-by-ball: {[f'{o.runs}' if not o.is_wicket else 'W' for o in outcomes]}")

    print(f"\n{num_overs} overs summary:")
    print(f"  Average runs/over: {mean(over_runs):.2f}")
    print(f"  Average wickets/over: {mean(over_wickets):.2f}")
    print(f"  Wicket rate per ball: {sum(over_wickets) / (sum(balls_per_over)) * 100:.2f}%")
    print(f"  Runs distribution: {Counter(over_runs).most_common(10)}")
    print(f"  Wickets distribution: {Counter(over_wickets)}")


def test_full_innings():
    """Test full innings simulation"""
    print("\n" + "="*70)
    print("TEST 4: FULL INNINGS SIMULATION")
    print("="*70)

    team1 = generate_test_team(1)
    team2 = generate_test_team(100)

    num_innings = 30
    scores = []
    wickets_list = []
    overs_list = []

    for i in range(num_innings):
        engine = MatchEngine()
        innings = engine.setup_innings(team1, team2)
        innings.context.pitch_type = "flat_deck"

        # Initialize batter states
        innings.batter_states[innings.striker_id] = BatterState(player_id=innings.striker_id)
        innings.batter_states[innings.non_striker_id] = BatterState(player_id=innings.non_striker_id)

        engine.simulate_innings(innings)

        scores.append(innings.total_runs)
        wickets_list.append(innings.wickets)
        overs_list.append(innings.overs + innings.balls/6)

        if i < 5:
            print(f"Innings {i+1}: {innings.total_runs}/{innings.wickets} in {innings.overs_display} overs")

    print(f"\n{num_innings} innings summary:")
    print(f"  Average score: {mean(scores):.1f}")
    print(f"  Score range: {min(scores)} - {max(scores)}")
    print(f"  Average wickets: {mean(wickets_list):.1f}")
    print(f"  Average overs: {mean(overs_list):.1f}")

    # Check how many innings had collapses (all out for < 100)
    collapses = sum(1 for s in scores if s < 100)
    print(f"  Collapses (< 100): {collapses} ({collapses/num_innings*100:.1f}%)")

    # Check realistic score distribution
    below_150 = sum(1 for s in scores if s < 150)
    between_150_180 = sum(1 for s in scores if 150 <= s < 180)
    above_180 = sum(1 for s in scores if s >= 180)
    print(f"  Below 150: {below_150} ({below_150/num_innings*100:.1f}%)")
    print(f"  150-180: {between_150_180} ({between_150_180/num_innings*100:.1f}%)")
    print(f"  Above 180: {above_180} ({above_180/num_innings*100:.1f}%)")


def test_margin_distribution():
    """Debug test to see actual margin distributions"""
    print("\n" + "="*70)
    print("TEST 5: MARGIN DISTRIBUTION ANALYSIS")
    print("="*70)

    batter = create_player(1, "Test Batter", PlayerRole.BATSMAN, batting=70, bowling=25, power=65)
    batter2 = create_player(2, "Non-Striker", PlayerRole.BATSMAN, batting=68, bowling=25, power=62)
    bowler = create_player(3, "Test Bowler", PlayerRole.BOWLER, batting=30, bowling=70, power=35)

    print("\nCalculation breakdown for BALANCED mode:")
    print(f"  Bowler bowling stat: {bowler.bowling}")
    print(f"  Bowling difficulty (before modifiers): {int(bowler.bowling * 0.78)}")

    print(f"\n  Batter batting stat: {batter.batting}")
    print(f"  Batting base: {batter.batting // 3}")
    print(f"  Batting variable max: {int(batter.batting * 2 // 3 * 1.0)}")
    print(f"  Batting roll range: {batter.batting // 3} to {batter.batting // 3 + int(batter.batting * 2 // 3)}")

    # Calculate margins
    bowling_diff = int(bowler.bowling * 0.78)  # 54.6 -> 54
    batting_base = batter.batting // 3  # 23
    batting_var = int(batter.batting * 2 // 3)  # 46

    min_margin = batting_base - bowling_diff
    max_margin = batting_base + batting_var - bowling_diff

    print(f"\n  Margin range: {min_margin} to {max_margin}")
    print(f"  (Negative margin = bowler wins)")

    # With pitch and state modifiers
    print("\n  With GREEN TOP pitch (+8 for pace bowler):")
    bowling_diff_green = bowling_diff + 8
    print(f"    New margin range: {batting_base - bowling_diff_green} to {batting_base + batting_var - bowling_diff_green}")

    print("\n  With FLAT DECK pitch (-3):")
    bowling_diff_flat = bowling_diff - 3
    print(f"    New margin range: {batting_base - bowling_diff_flat} to {batting_base + batting_var - bowling_diff_flat}")


if __name__ == "__main__":
    test_margin_distribution()
    test_single_ball_outcomes(1000)
    test_with_state_effects(500)
    test_simulate_over()
    test_full_innings()
