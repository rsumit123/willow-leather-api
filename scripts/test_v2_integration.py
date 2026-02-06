#!/usr/bin/env python3
"""
Integration test for Match Engine v2 with DB players.
Validates that the v2 engine works correctly with SQLAlchemy Player objects
that have DNA attributes.

Run: python scripts/test_v2_integration.py [num_matches]
"""
import sys
import os
import random
from collections import defaultdict
from statistics import mean

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session, Base, engine as db_engine
from app.generators.player_generator import PlayerGenerator
from app.models.player import Player, PlayerRole
from app.engine.match_engine_v2 import MatchEngineV2
from app.engine.dna import PITCHES


def build_team(players: list[Player]) -> list[Player]:
    """Build a realistic XI from a pool of players."""
    wks = [p for p in players if p.role == PlayerRole.WICKET_KEEPER]
    bats = [p for p in players if p.role == PlayerRole.BATSMAN]
    ars = [p for p in players if p.role == PlayerRole.ALL_ROUNDER]
    bowls = [p for p in players if p.role == PlayerRole.BOWLER]

    team = []
    if wks:
        team.append(wks.pop(0))
    team.extend(bats[:4])
    bats = bats[4:]
    team.extend(ars[:2])
    ars = ars[2:]
    team.extend(bowls[:4])
    bowls = bowls[4:]

    remaining = wks + bats + ars + bowls
    while len(team) < 11 and remaining:
        team.append(remaining.pop(0))

    return team[:11]


def run_test(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"  {color}[{status}]{reset} {name}", end="")
    if detail:
        print(f"  ({detail})", end="")
    print()
    return passed


def main():
    num_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(f"\n{'='*60}")
    print(f"  Match Engine v2 Integration Test ({num_matches} matches)")
    print(f"{'='*60}\n")

    # Initialize DB
    print("Setting up database...")
    init_db()

    session = get_session()

    # Generate players if needed
    players = session.query(Player).all()
    if len(players) < 50:
        print("Generating player pool...")
        new_players = PlayerGenerator.generate_player_pool(100)
        for p in new_players:
            session.add(p)
        session.commit()
        players = session.query(Player).all()

    print(f"Player pool: {len(players)} players")

    # Check DNA is populated
    dna_count = sum(1 for p in players if p.batting_dna_json is not None)
    bowler_dna_count = sum(1 for p in players if p.bowler_dna_json is not None)
    print(f"Players with batting DNA: {dna_count}/{len(players)}")
    print(f"Players with bowler DNA: {bowler_dna_count}/{len(players)}")

    results = []
    all_passed = 0
    all_total = 0

    # =============================================
    # TEST 1: DNA Deserialization
    # =============================================
    print("\n--- Test Category 1: DNA Deserialization ---")

    sample = players[0]
    dna = sample.batting_dna
    t = run_test("BatterDNA deserialization", dna is not None,
                 f"vs_pace={dna.vs_pace}" if dna else "None")
    all_total += 1
    all_passed += int(t)

    bowler = next((p for p in players if p.role == PlayerRole.BOWLER), None)
    if bowler:
        bdna = bowler.bowler_dna
        t = run_test("BowlerDNA deserialization", bdna is not None,
                     f"type={'pacer' if hasattr(bdna, 'speed') else 'spinner'}" if bdna else "None")
        all_total += 1
        all_passed += int(t)

    # =============================================
    # TEST 2: Match Simulation
    # =============================================
    print("\n--- Test Category 2: Match Simulation ---")

    stats = defaultdict(list)
    engine = MatchEngineV2()

    for i in range(num_matches):
        random.shuffle(players)
        team1 = build_team(players[:50])
        team2 = build_team(players[50:100])

        result = engine.simulate_match(team1, team2)

        stats["scores"].append(result["innings1"]["runs"])
        stats["scores"].append(result["innings2"]["runs"])
        stats["wickets"].append(result["innings1"]["wickets"])
        stats["wickets"].append(result["innings2"]["wickets"])
        stats["chasing_wins"].append(1 if result["winner"] == "team2" else 0)

    avg_score = mean(stats["scores"])
    min_score = min(stats["scores"])
    max_score = max(stats["scores"])
    avg_wkts = mean(stats["wickets"])
    chase_pct = mean(stats["chasing_wins"]) * 100

    t = run_test("Average score in T20 range (120-200)",
                 120 <= avg_score <= 200,
                 f"avg={avg_score:.1f}")
    all_total += 1; all_passed += int(t)

    t = run_test("No unrealistic collapses (min > 20)",
                 min_score > 20,
                 f"min={min_score}")
    all_total += 1; all_passed += int(t)

    t = run_test("Max score < 300",
                 max_score < 300,
                 f"max={max_score}")
    all_total += 1; all_passed += int(t)

    t = run_test("Average wickets 4-9",
                 4 <= avg_wkts <= 9,
                 f"avg={avg_wkts:.1f}")
    all_total += 1; all_passed += int(t)

    t = run_test("Chasing win% 30-70%",
                 30 <= chase_pct <= 70,
                 f"{chase_pct:.1f}%")
    all_total += 1; all_passed += int(t)

    # =============================================
    # TEST 3: Pitch Differentiation
    # =============================================
    print("\n--- Test Category 3: Pitch Differentiation ---")

    pitch_scores = {}
    for pitch_name, pitch in PITCHES.items():
        p_scores = []
        for _ in range(30):
            random.shuffle(players)
            team1 = build_team(players[:50])
            team2 = build_team(players[50:100])
            engine = MatchEngineV2()
            result = engine.simulate_match(team1, team2, pitch=pitch)
            p_scores.append(result["innings1"]["runs"])
            # Only count 2nd innings if it wasn't a short chase
            if result["innings2"]["wickets"] == 10 or result["innings2"]["overs"] == "20.0":
                p_scores.append(result["innings2"]["runs"])
        pitch_scores[pitch_name] = mean(p_scores)

    # Green seamer should have lower avg score than flat deck
    t = run_test("Green seamer < flat deck score",
                 pitch_scores["green_seamer"] < pitch_scores["flat_deck"],
                 f"green={pitch_scores['green_seamer']:.0f}, flat={pitch_scores['flat_deck']:.0f}")
    all_total += 1; all_passed += int(t)

    # Dust bowl should have lower score than flat deck
    t = run_test("Dust bowl < flat deck score",
                 pitch_scores["dust_bowl"] < pitch_scores["flat_deck"],
                 f"dust={pitch_scores['dust_bowl']:.0f}, flat={pitch_scores['flat_deck']:.0f}")
    all_total += 1; all_passed += int(t)

    # =============================================
    # TEST 4: Commentary & Outcomes
    # =============================================
    print("\n--- Test Category 4: Ball Outcomes ---")

    random.shuffle(players)
    team1 = build_team(players[:50])
    team2 = build_team(players[50:100])
    engine = MatchEngineV2()
    innings = engine.setup_innings(team1, team2, pitch=PITCHES["balanced"])
    engine.current_innings = innings

    bowler = engine.select_bowler(innings)
    innings.current_bowler_id = bowler.id
    outcomes = engine.simulate_over(innings, "balanced")

    has_commentary = all(o.commentary for o in outcomes)
    t = run_test("All outcomes have commentary",
                 has_commentary,
                 f"{len(outcomes)} balls")
    all_total += 1; all_passed += int(t)

    has_delivery = all(o.delivery_name or o.is_wide or o.is_no_ball for o in outcomes)
    t = run_test("All legal deliveries have delivery_name",
                 has_delivery)
    all_total += 1; all_passed += int(t)

    # =============================================
    # TEST 5: Aggression modes
    # =============================================
    print("\n--- Test Category 5: Aggression Modes ---")

    agg_srs = {}
    for agg in ["defend", "balanced", "attack"]:
        runs_total = 0
        balls_total = 0
        for _ in range(30):
            random.shuffle(players)
            team1 = build_team(players[:50])
            team2 = build_team(players[50:100])
            engine = MatchEngineV2()
            innings = engine.setup_innings(team1, team2, pitch=PITCHES["balanced"])

            # Simulate 5 overs with this aggression
            for _ in range(5):
                if innings.is_innings_complete:
                    break
                engine.simulate_over(innings, agg)

            runs_total += innings.total_runs
            balls_total += innings.overs * 6 + innings.balls

        sr = (runs_total / balls_total) * 100 if balls_total > 0 else 0
        agg_srs[agg] = sr

    t = run_test("Attack SR > Balanced SR",
                 agg_srs["attack"] > agg_srs["balanced"],
                 f"attack={agg_srs['attack']:.1f}, balanced={agg_srs['balanced']:.1f}")
    all_total += 1; all_passed += int(t)

    t = run_test("Balanced SR > Defend SR",
                 agg_srs["balanced"] > agg_srs["defend"],
                 f"balanced={agg_srs['balanced']:.1f}, defend={agg_srs['defend']:.1f}")
    all_total += 1; all_passed += int(t)

    # =============================================
    # SUMMARY
    # =============================================
    print(f"\n{'='*60}")
    color = "\033[92m" if all_passed == all_total else "\033[93m"
    reset = "\033[0m"
    print(f"  {color}Results: {all_passed}/{all_total} tests passed{reset}")
    print(f"{'='*60}\n")

    session.close()
    return 0 if all_passed == all_total else 1


if __name__ == "__main__":
    sys.exit(main())
