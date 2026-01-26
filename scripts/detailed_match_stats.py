#!/usr/bin/env python3
"""
Detailed match statistics after running simulations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.match_engine import MatchEngine
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle
from collections import defaultdict

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
        (PlayerRole.BATSMAN, BowlingType.NONE, "Opener"),
        (PlayerRole.BATSMAN, BowlingType.NONE, "Opener"),
        (PlayerRole.BATSMAN, BowlingType.NONE, "Top Order"),
        (PlayerRole.BATSMAN, BowlingType.NONE, "Middle Order"),
        (PlayerRole.ALL_ROUNDER, BowlingType.MEDIUM, "All-Rounder"),
        (PlayerRole.ALL_ROUNDER, BowlingType.OFF_SPIN, "All-Rounder"),
        (PlayerRole.WICKET_KEEPER, BowlingType.NONE, "Keeper"),
        (PlayerRole.BOWLER, BowlingType.PACE, "Pace Bowler"),
        (PlayerRole.BOWLER, BowlingType.PACE, "Pace Bowler"),
        (PlayerRole.BOWLER, BowlingType.LEG_SPIN, "Spinner"),
        (PlayerRole.BOWLER, BowlingType.OFF_SPIN, "Spinner"),
    ]

    for i, (role, bowl_type, pos) in enumerate(roles):
        bat_skill = base_bat + (15 if role in [PlayerRole.BATSMAN, PlayerRole.ALL_ROUNDER] else 0)
        bowl_skill = base_bowl + (10 if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER] else 0)

        player = Player(
            id=i + 1,
            name=f"{pos}_{i+1}",
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


def run_detailed_simulations(num_matches: int = 50):
    """Run simulations and collect detailed stats"""

    batting_team = create_team("balanced")
    bowling_team = create_team("balanced")

    # Aggregate stats
    total_scores = []
    total_wickets = []
    total_overs = []
    total_boundaries = []
    total_sixes = []
    total_dots = []

    batsman_runs = defaultdict(list)
    batsman_balls = defaultdict(list)
    batsman_dismissals = defaultdict(int)

    bowler_wickets = defaultdict(list)
    bowler_runs = defaultdict(list)
    bowler_overs = defaultdict(list)

    for match_num in range(num_matches):
        engine = MatchEngine()
        innings = engine.setup_innings(batting_team, bowling_team)

        # Track ball-by-ball stats
        boundaries = 0
        sixes = 0
        dots = 0

        while not innings.is_innings_complete:
            outcomes = engine.simulate_over(innings, "balanced")
            for outcome in outcomes:
                if outcome.is_six:
                    sixes += 1
                    boundaries += 1
                elif outcome.is_boundary:
                    boundaries += 1
                elif outcome.runs == 0 and not outcome.is_wide and not outcome.is_no_ball:
                    dots += 1

        total_scores.append(innings.total_runs)
        total_wickets.append(innings.wickets)
        total_overs.append(innings.overs + innings.balls / 6)
        total_boundaries.append(boundaries)
        total_sixes.append(sixes)
        total_dots.append(dots)

        # Collect batsman stats
        for player_id, batter_innings in innings.batter_innings.items():
            player_name = batter_innings.player.name
            batsman_runs[player_name].append(batter_innings.runs)
            batsman_balls[player_name].append(batter_innings.balls)
            if batter_innings.is_out:
                batsman_dismissals[player_name] += 1

        # Collect bowler stats
        for player_id, spell in innings.bowler_spells.items():
            player_name = spell.player.name
            bowler_wickets[player_name].append(spell.wickets)
            bowler_runs[player_name].append(spell.runs)
            bowler_overs[player_name].append(spell.overs + spell.balls / 6)

    # Print results
    print("=" * 70)
    print(f"DETAILED MATCH STATISTICS ({num_matches} innings simulated)")
    print("=" * 70)

    print("\n### INNINGS SUMMARY ###")
    print(f"Average Score:        {sum(total_scores) / len(total_scores):.1f} runs")
    print(f"Min Score:            {min(total_scores)} runs")
    print(f"Max Score:            {max(total_scores)} runs")
    print(f"Average Wickets:      {sum(total_wickets) / len(total_wickets):.1f}")
    print(f"Average Overs:        {sum(total_overs) / len(total_overs):.1f}")
    print(f"All-Out Rate:         {sum(1 for w in total_wickets if w >= 10) / len(total_wickets) * 100:.1f}%")

    avg_rr = sum(s / o if o > 0 else 0 for s, o in zip(total_scores, total_overs)) / len(total_scores)
    print(f"Average Run Rate:     {avg_rr:.2f}")

    print(f"\nAvg Boundaries/Inn:   {sum(total_boundaries) / len(total_boundaries):.1f}")
    print(f"Avg Sixes/Inn:        {sum(total_sixes) / len(total_sixes):.1f}")
    print(f"Avg Dot Balls/Inn:    {sum(total_dots) / len(total_dots):.1f}")

    total_balls = sum(o * 6 for o in total_overs)
    total_all_wickets = sum(total_wickets)
    wicket_rate = (total_all_wickets / total_balls) * 100 if total_balls > 0 else 0
    print(f"Wicket Rate:          {wicket_rate:.2f}% per ball")

    print("\n### BATTING STATISTICS (by position) ###")
    print(f"{'Player':<20} {'Innings':<8} {'Runs':<8} {'Avg':<8} {'Balls':<8} {'SR':<8} {'Dismissals':<10}")
    print("-" * 70)

    # Sort by batting order (use player ID from name)
    sorted_batsmen = sorted(batsman_runs.keys(), key=lambda x: int(x.split('_')[1]))

    for player in sorted_batsmen:
        runs = batsman_runs[player]
        balls = batsman_balls[player]
        dismissals = batsman_dismissals[player]

        total_runs = sum(runs)
        total_balls = sum(balls)
        innings_count = len(runs)
        avg = total_runs / dismissals if dismissals > 0 else total_runs
        sr = (total_runs / total_balls * 100) if total_balls > 0 else 0

        print(f"{player:<20} {innings_count:<8} {total_runs:<8} {avg:<8.1f} {total_balls:<8} {sr:<8.1f} {dismissals:<10}")

    print("\n### BOWLING STATISTICS ###")
    print(f"{'Player':<20} {'Innings':<8} {'Overs':<8} {'Runs':<8} {'Wickets':<8} {'Avg':<8} {'Econ':<8}")
    print("-" * 70)

    sorted_bowlers = sorted(bowler_wickets.keys(), key=lambda x: sum(bowler_wickets[x]), reverse=True)

    for player in sorted_bowlers:
        wickets = bowler_wickets[player]
        runs = bowler_runs[player]
        overs = bowler_overs[player]

        total_wickets_b = sum(wickets)
        total_runs_b = sum(runs)
        total_overs_b = sum(overs)
        innings_count = len(wickets)
        avg = total_runs_b / total_wickets_b if total_wickets_b > 0 else 0
        econ = total_runs_b / total_overs_b if total_overs_b > 0 else 0

        print(f"{player:<20} {innings_count:<8} {total_overs_b:<8.1f} {total_runs_b:<8} {total_wickets_b:<8} {avg:<8.1f} {econ:<8.2f}")

    print("\n" + "=" * 70)

    # Score distribution
    print("\n### SCORE DISTRIBUTION ###")
    ranges = [(0, 100), (100, 125), (125, 150), (150, 175), (175, 200), (200, 260)]
    for low, high in ranges:
        count = sum(1 for s in total_scores if low <= s < high)
        pct = count / len(total_scores) * 100
        bar = '#' * int(pct / 2)
        print(f"{low:3}-{high:3}: {count:3} ({pct:5.1f}%) {bar}")

    print("=" * 70)


if __name__ == "__main__":
    run_detailed_simulations(50)
