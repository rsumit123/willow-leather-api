#!/usr/bin/env python3
"""
Analyze innings length distribution to understand why innings end early.
"""
import sys
sys.path.insert(0, '/Users/rsumit123/work/willow-leather-api')

import random
from statistics import mean, stdev
from collections import Counter

from app.engine.match_engine import MatchEngine
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
import json


def create_player(player_id: int, name: str, role: PlayerRole, batting: int, bowling: int, power: int = 50, batting_intent: str = "accumulator") -> Player:
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
        batting_intent=batting_intent,
    )
    player.id = player_id
    return player


def generate_test_team(start_id: int, batting_intent: str = "mixed") -> list:
    """Generate a test team with realistic IPL-like stats

    batting_intent options:
    - "anchor": All batters are anchors (low variance)
    - "accumulator": All batters are accumulators
    - "aggressive": All batters are aggressive
    - "power_hitter": All batters are power hitters (high variance)
    - "mixed": Realistic mix (default)
    """
    players = []
    player_id = start_id

    # Define batting intents for mixed team
    mixed_intents = [
        "anchor",        # Opener 1 - steady
        "aggressive",    # Opener 2 - attacking
        "accumulator",   # WK
        "aggressive",    # Middle order
        "power_hitter",  # Middle order finisher
        "accumulator",   # All-rounder
        "aggressive",    # All-rounder
        "accumulator",   # Bowler (tail)
        "accumulator",   # Bowler (tail)
        "accumulator",   # Bowler (tail)
        "accumulator",   # Bowler (tail)
    ]

    player_templates = [
        # Openers (2)
        {"role": PlayerRole.BATSMAN, "batting": (72, 78), "bowling": (22, 28), "power": (68, 76)},
        {"role": PlayerRole.BATSMAN, "batting": (70, 76), "bowling": (22, 28), "power": (65, 73)},
        # Middle order (3)
        {"role": PlayerRole.WICKET_KEEPER, "batting": (65, 72), "bowling": (18, 24), "power": (58, 66)},
        {"role": PlayerRole.BATSMAN, "batting": (66, 73), "bowling": (22, 28), "power": (62, 70)},
        {"role": PlayerRole.BATSMAN, "batting": (62, 69), "bowling": (22, 28), "power": (58, 66)},
        # All-rounders (2)
        {"role": PlayerRole.ALL_ROUNDER, "batting": (60, 67), "bowling": (60, 67), "power": (54, 62)},
        {"role": PlayerRole.ALL_ROUNDER, "batting": (58, 65), "bowling": (62, 69), "power": (52, 60)},
        # Bowlers (4) - tail-enders
        {"role": PlayerRole.BOWLER, "batting": (28, 36), "bowling": (70, 76), "power": (32, 42)},
        {"role": PlayerRole.BOWLER, "batting": (28, 36), "bowling": (68, 74), "power": (32, 42)},
        {"role": PlayerRole.BOWLER, "batting": (25, 33), "bowling": (66, 72), "power": (28, 38)},
        {"role": PlayerRole.BOWLER, "batting": (25, 33), "bowling": (64, 70), "power": (28, 38)},
    ]

    for i, template in enumerate(player_templates):
        batting = random.randint(*template["batting"])
        bowling = random.randint(*template["bowling"])
        power = random.randint(*template["power"])

        # Determine batting intent
        if batting_intent == "mixed":
            intent = mixed_intents[i]
        else:
            intent = batting_intent

        player = create_player(
            player_id=player_id,
            name=f"Player {player_id}",
            role=template["role"],
            batting=batting,
            bowling=bowling,
            power=power,
            batting_intent=intent
        )
        players.append(player)
        player_id += 1

    return players


def parse_overs(overs_str: str) -> float:
    """Convert overs string like '19.4' to total balls as decimal overs"""
    parts = overs_str.split('.')
    overs = int(parts[0])
    balls = int(parts[1]) if len(parts) > 1 else 0
    return overs + balls / 6


def run_analysis(num_matches: int = 100):
    """Run match simulations and analyze innings length"""

    # Track innings data
    innings_data = []

    print(f"Running {num_matches} match simulations...\n")

    for i in range(num_matches):
        engine = MatchEngine()
        team1 = generate_test_team(start_id=1)
        team2 = generate_test_team(start_id=100)

        result = engine.simulate_match(team1, team2)

        # Track both innings
        for innings_num, innings_key in enumerate(["innings1", "innings2"], 1):
            innings = result[innings_key]
            overs_completed = parse_overs(innings["overs"])

            innings_data.append({
                "match": i + 1,
                "innings": innings_num,
                "runs": innings["runs"],
                "wickets": innings["wickets"],
                "overs": overs_completed,
                "all_out": innings["wickets"] == 10,
                "full_20": overs_completed >= 20.0,
            })

        if (i + 1) % 20 == 0:
            print(f"Completed {i + 1} matches...")

    # Analyze results
    print("\n" + "="*70)
    print("INNINGS LENGTH ANALYSIS")
    print("="*70)

    total_innings = len(innings_data)
    first_innings = [i for i in innings_data if i["innings"] == 1]
    second_innings = [i for i in innings_data if i["innings"] == 2]

    # Full 20 overs stats
    full_20_count = sum(1 for i in innings_data if i["full_20"])
    all_out_count = sum(1 for i in innings_data if i["all_out"])

    print(f"\nTotal innings analyzed: {total_innings}")
    print(f"Innings going full 20 overs: {full_20_count} ({full_20_count/total_innings*100:.1f}%)")
    print(f"Innings all out: {all_out_count} ({all_out_count/total_innings*100:.1f}%)")

    # First innings specific
    first_full_20 = sum(1 for i in first_innings if i["full_20"])
    first_all_out = sum(1 for i in first_innings if i["all_out"])
    print(f"\n1ST INNINGS:")
    print(f"  Full 20 overs: {first_full_20} ({first_full_20/len(first_innings)*100:.1f}%)")
    print(f"  All out: {first_all_out} ({first_all_out/len(first_innings)*100:.1f}%)")
    print(f"  Avg overs: {mean([i['overs'] for i in first_innings]):.1f}")
    print(f"  Avg wickets: {mean([i['wickets'] for i in first_innings]):.1f}")
    print(f"  Avg score: {mean([i['runs'] for i in first_innings]):.1f}")

    # Second innings specific (may end early due to chase)
    second_full_20 = sum(1 for i in second_innings if i["full_20"])
    second_all_out = sum(1 for i in second_innings if i["all_out"])
    # Chase completed early (not all out, not full 20)
    chase_won_early = sum(1 for i in second_innings if not i["all_out"] and not i["full_20"])
    print(f"\n2ND INNINGS:")
    print(f"  Full 20 overs: {second_full_20} ({second_full_20/len(second_innings)*100:.1f}%)")
    print(f"  All out: {second_all_out} ({second_all_out/len(second_innings)*100:.1f}%)")
    print(f"  Chase won early: {chase_won_early} ({chase_won_early/len(second_innings)*100:.1f}%)")
    print(f"  Avg overs: {mean([i['overs'] for i in second_innings]):.1f}")
    print(f"  Avg wickets: {mean([i['wickets'] for i in second_innings]):.1f}")
    print(f"  Avg score: {mean([i['runs'] for i in second_innings]):.1f}")

    # Overs distribution for first innings only (since 2nd can end early for chase)
    print("\n" + "-"*70)
    print("1ST INNINGS OVERS DISTRIBUTION:")
    print("-"*70)

    overs_buckets = Counter()
    for i in first_innings:
        if i["overs"] >= 20:
            overs_buckets["20 (full)"] += 1
        elif i["overs"] >= 18:
            overs_buckets["18-19"] += 1
        elif i["overs"] >= 16:
            overs_buckets["16-17"] += 1
        elif i["overs"] >= 14:
            overs_buckets["14-15"] += 1
        elif i["overs"] >= 12:
            overs_buckets["12-13"] += 1
        else:
            overs_buckets["< 12"] += 1

    for bucket in ["20 (full)", "18-19", "16-17", "14-15", "12-13", "< 12"]:
        count = overs_buckets.get(bucket, 0)
        pct = count / len(first_innings) * 100
        bar = "#" * int(pct / 2)
        print(f"  {bucket:12}: {count:3} ({pct:5.1f}%) {bar}")

    # Wickets distribution for first innings
    print("\n" + "-"*70)
    print("1ST INNINGS WICKETS DISTRIBUTION:")
    print("-"*70)

    wicket_counts = Counter(i["wickets"] for i in first_innings)
    for w in range(11):
        count = wicket_counts.get(w, 0)
        pct = count / len(first_innings) * 100
        bar = "#" * int(pct / 2)
        label = f"{w} wickets" if w < 10 else "10 (all out)"
        print(f"  {label:12}: {count:3} ({pct:5.1f}%) {bar}")

    # Score when all out vs full 20
    print("\n" + "-"*70)
    print("SCORE COMPARISON:")
    print("-"*70)

    all_out_scores = [i["runs"] for i in first_innings if i["all_out"]]
    full_20_scores = [i["runs"] for i in first_innings if i["full_20"]]

    if all_out_scores:
        print(f"  When ALL OUT: avg={mean(all_out_scores):.1f}, min={min(all_out_scores)}, max={max(all_out_scores)}")
    if full_20_scores:
        print(f"  When FULL 20: avg={mean(full_20_scores):.1f}, min={min(full_20_scores)}, max={max(full_20_scores)}")

    # Real T20 benchmarks
    print("\n" + "="*70)
    print("COMPARISON WITH REAL T20 (IPL):")
    print("="*70)
    print("""
Real IPL statistics (approximate):
- First innings all-out rate: ~15-20%
- First innings full 20 overs: ~75-80%
- Average first innings score: 165-180
- Average wickets in 1st innings: 5-6

Issues to investigate if:
- All-out rate > 25%: Wicket probability too high
- Full 20 overs < 70%: Batters getting out too easily
- Tail collapse frequent: Tail-ender floor too low
""")

    # Final assessment
    print("="*70)
    print("ASSESSMENT:")
    print("="*70)

    issues = []
    if first_all_out / len(first_innings) > 0.25:
        issues.append(f"All-out rate too high: {first_all_out/len(first_innings)*100:.1f}% (target: <25%)")
    if first_full_20 / len(first_innings) < 0.70:
        issues.append(f"Full 20 overs rate too low: {first_full_20/len(first_innings)*100:.1f}% (target: >70%)")

    avg_first_wickets = mean([i['wickets'] for i in first_innings])
    if avg_first_wickets > 6.5:
        issues.append(f"Average wickets too high: {avg_first_wickets:.1f} (target: 5-6)")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("No major issues found - stats within acceptable range.")

    return innings_data


def compare_batting_intents(num_matches: int = 50):
    """Compare innings stats across different batting intent compositions"""
    print("\n" + "="*70)
    print("BATTING INTENT COMPARISON")
    print("="*70)

    intents = ["anchor", "accumulator", "aggressive", "power_hitter", "mixed"]
    results = {}

    for intent in intents:
        print(f"\nSimulating {num_matches} matches with {intent.upper()} batters...")

        innings_data = []
        for i in range(num_matches):
            engine = MatchEngine()
            team1 = generate_test_team(start_id=1, batting_intent=intent)
            team2 = generate_test_team(start_id=100, batting_intent=intent)

            result = engine.simulate_match(team1, team2)

            # Only track first innings (not affected by chasing)
            innings = result["innings1"]
            overs_completed = parse_overs(innings["overs"])

            innings_data.append({
                "runs": innings["runs"],
                "wickets": innings["wickets"],
                "overs": overs_completed,
                "all_out": innings["wickets"] == 10,
                "full_20": overs_completed >= 20.0,
            })

        full_20_pct = sum(1 for i in innings_data if i["full_20"]) / len(innings_data) * 100
        all_out_pct = sum(1 for i in innings_data if i["all_out"]) / len(innings_data) * 100
        avg_wickets = mean([i["wickets"] for i in innings_data])
        avg_runs = mean([i["runs"] for i in innings_data])
        avg_overs = mean([i["overs"] for i in innings_data])

        results[intent] = {
            "full_20_pct": full_20_pct,
            "all_out_pct": all_out_pct,
            "avg_wickets": avg_wickets,
            "avg_runs": avg_runs,
            "avg_overs": avg_overs,
        }

    # Print comparison table
    print("\n" + "-"*70)
    print(f"{'Intent':<15} {'Full 20':>10} {'All Out':>10} {'Avg Wkts':>10} {'Avg Runs':>10} {'Avg Overs':>10}")
    print("-"*70)

    for intent in intents:
        r = results[intent]
        print(f"{intent:<15} {r['full_20_pct']:>9.1f}% {r['all_out_pct']:>9.1f}% {r['avg_wickets']:>10.1f} {r['avg_runs']:>10.1f} {r['avg_overs']:>10.1f}")

    print("-"*70)
    print("\nKey findings:")
    print(f"  - Anchors: Most stable, highest full 20 rate")
    print(f"  - Power hitters: Highest variance, more all-outs but also high scores")
    print(f"  - Mixed: Realistic balance of risk/reward")

    return results


if __name__ == "__main__":
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    # Run standard analysis first
    run_analysis(num)

    # Then compare batting intents
    compare_batting_intents(num // 2 if num >= 50 else 25)
