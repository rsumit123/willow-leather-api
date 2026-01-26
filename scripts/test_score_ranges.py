#!/usr/bin/env python3
"""
Test script to verify match engine produces realistic score ranges.

Run with: python scripts/test_score_ranges.py

Success Criteria:
- Min score: >= 50 in all scenarios
- Max score: <= 260 in all scenarios
- Avg score: 140-180 for balanced
- Wicket rate: 3-6% per ball
- All-out rate: < 30% of innings
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.match_engine import MatchEngine
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle

# Create mock players with different skill levels
def create_team(skill_level: str) -> list[Player]:
    """Create a team with given skill level: 'weak', 'balanced', 'strong'"""
    skill_map = {
        'weak': (55, 60),
        'balanced': (70, 75),
        'strong': (85, 85)
    }
    base_bat, base_bowl = skill_map[skill_level]

    players = []
    roles = [
        (PlayerRole.BATSMAN, BowlingType.NONE),
        (PlayerRole.BATSMAN, BowlingType.NONE),
        (PlayerRole.BATSMAN, BowlingType.NONE),
        (PlayerRole.BATSMAN, BowlingType.NONE),
        (PlayerRole.ALL_ROUNDER, BowlingType.MEDIUM),
        (PlayerRole.ALL_ROUNDER, BowlingType.OFF_SPIN),
        (PlayerRole.WICKET_KEEPER, BowlingType.NONE),
        (PlayerRole.BOWLER, BowlingType.PACE),
        (PlayerRole.BOWLER, BowlingType.PACE),
        (PlayerRole.BOWLER, BowlingType.LEG_SPIN),
        (PlayerRole.BOWLER, BowlingType.OFF_SPIN),
    ]

    for i, (role, bowl_type) in enumerate(roles):
        bat_skill = base_bat + (15 if role in [PlayerRole.BATSMAN, PlayerRole.ALL_ROUNDER] else 0)
        bowl_skill = base_bowl + (10 if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER] else 0)

        player = Player(
            id=i + 1,
            name=f"Player_{i+1}",
            age=25,
            nationality="Test",
            is_overseas=False,
            role=role,
            batting_style=BattingStyle.RIGHT_HANDED,
            bowling_type=bowl_type,
            batting=max(40, min(99, bat_skill)),
            bowling=max(40, min(99, bowl_skill)),
            fielding=70,
            fitness=70,
            power=70,
            technique=70,
            running=70,
            pace_or_spin=70,
            accuracy=70,
            variation=70,
            temperament=70,
            consistency=70,
            form=1.0,
            base_price=100000,
        )
        players.append(player)

    return players


SCENARIOS = {
    "attack_mode": {"aggression": "attack", "batting": "balanced", "bowling": "balanced"},
    "defend_mode": {"aggression": "defend", "batting": "balanced", "bowling": "balanced"},
    "balanced_mode": {"aggression": "balanced", "batting": "balanced", "bowling": "balanced"},
    "weak_vs_strong": {"aggression": "balanced", "batting": "weak", "bowling": "strong"},
    "strong_vs_weak": {"aggression": "balanced", "batting": "strong", "bowling": "weak"},
}

NUM_MATCHES = 50


def run_scenario(scenario_name: str, config: dict) -> dict:
    """Run matches for a scenario and collect stats"""
    batting_team = create_team(config["batting"])
    bowling_team = create_team(config["bowling"])
    aggression = config["aggression"]

    scores = []
    wickets = []
    all_outs = 0
    total_balls = 0
    total_wickets = 0

    for _ in range(NUM_MATCHES):
        engine = MatchEngine()
        innings = engine.setup_innings(batting_team, bowling_team)

        # Simulate innings
        while not innings.is_innings_complete:
            engine.simulate_over(innings, aggression)

        scores.append(innings.total_runs)
        wickets.append(innings.wickets)

        if innings.wickets >= 10:
            all_outs += 1

        balls_faced = innings.overs * 6 + innings.balls
        total_balls += balls_faced
        total_wickets += innings.wickets

    return {
        "min_score": min(scores),
        "max_score": max(scores),
        "avg_score": sum(scores) / len(scores),
        "scores_below_50": sum(1 for s in scores if s < 50),
        "scores_above_260": sum(1 for s in scores if s > 260),
        "wicket_rate": (total_wickets / total_balls) * 100 if total_balls > 0 else 0,
        "all_out_rate": (all_outs / NUM_MATCHES) * 100,
        "avg_wickets": sum(wickets) / len(wickets),
    }


def main():
    print("=" * 60)
    print("Match Engine Score Range Test")
    print(f"Running {NUM_MATCHES} matches per scenario")
    print("=" * 60)

    all_passed = True
    results = {}

    for scenario_name, config in SCENARIOS.items():
        print(f"\nRunning scenario: {scenario_name}...")
        stats = run_scenario(scenario_name, config)
        results[scenario_name] = stats

        # Check pass/fail criteria
        passed = True
        issues = []

        if stats["min_score"] < 50:
            passed = False
            issues.append(f"Min score {stats['min_score']} < 50")

        if stats["max_score"] > 260:
            passed = False
            issues.append(f"Max score {stats['max_score']} > 260")

        if stats["scores_below_50"] > 0:
            passed = False
            issues.append(f"{stats['scores_below_50']} scores below 50")

        if stats["scores_above_260"] > 0:
            passed = False
            issues.append(f"{stats['scores_above_260']} scores above 260")

        if stats["wicket_rate"] < 2 or stats["wicket_rate"] > 8:
            issues.append(f"Wicket rate {stats['wicket_rate']:.2f}% outside 2-8% range")

        if stats["all_out_rate"] > 40:
            issues.append(f"All-out rate {stats['all_out_rate']:.1f}% > 40%")

        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"  [{status}] {scenario_name}")
        print(f"    Score Range: {stats['min_score']}-{stats['max_score']} (avg: {stats['avg_score']:.1f})")
        print(f"    Wicket Rate: {stats['wicket_rate']:.2f}% per ball")
        print(f"    All-Out Rate: {stats['all_out_rate']:.1f}%")
        print(f"    Avg Wickets: {stats['avg_wickets']:.1f}")

        if issues:
            for issue in issues:
                print(f"    ! {issue}")

    print("\n" + "=" * 60)
    if all_passed:
        print("OVERALL: ALL SCENARIOS PASSED")
    else:
        print("OVERALL: SOME SCENARIOS FAILED")
        print("\nReview the issues above and adjust match_engine.py parameters.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
