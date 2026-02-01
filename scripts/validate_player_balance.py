#!/usr/bin/env python3
"""
Validate player balance after generation.
Run this after generating players to verify distributions are correct.

Usage:
    python scripts/validate_player_balance.py
"""
import json
from collections import Counter
from app.generators.player_generator import PlayerGenerator
from app.models.player import PlayerRole


def generate_with_tier_tracking():
    """Generate players while tracking their tiers."""
    players = []
    tier_map = {}  # player index -> tier

    # Generate elite players (20 total: 8 Indian, 12 overseas)
    for _ in range(8):
        p = PlayerGenerator.generate_player(tier="elite", nationality="India")
        tier_map[len(players)] = "elite"
        players.append(p)
    for _ in range(12):
        p = PlayerGenerator.generate_player(tier="elite", nationality=PlayerGenerator._random_overseas_nationality())
        tier_map[len(players)] = "elite"
        players.append(p)

    # Generate star players (40 total: 18 Indian, 22 overseas)
    for _ in range(18):
        p = PlayerGenerator.generate_player(tier="star", nationality="India")
        tier_map[len(players)] = "star"
        players.append(p)
    for _ in range(22):
        p = PlayerGenerator.generate_player(tier="star", nationality=PlayerGenerator._random_overseas_nationality())
        tier_map[len(players)] = "star"
        players.append(p)

    # Generate good players (80 total: 50 Indian, 30 overseas)
    for _ in range(50):
        p = PlayerGenerator.generate_player(tier="good", nationality="India")
        tier_map[len(players)] = "good"
        players.append(p)
    for _ in range(30):
        p = PlayerGenerator.generate_player(tier="good", nationality=PlayerGenerator._random_overseas_nationality())
        tier_map[len(players)] = "good"
        players.append(p)

    # Generate solid players (90 total: 74 Indian, 16 overseas)
    for _ in range(74):
        p = PlayerGenerator.generate_player(tier="solid", nationality="India")
        tier_map[len(players)] = "solid"
        players.append(p)
    for _ in range(16):
        p = PlayerGenerator.generate_player(tier="solid", nationality=PlayerGenerator._random_overseas_nationality())
        tier_map[len(players)] = "solid"
        players.append(p)

    return players, tier_map


def validate_distribution():
    """Generate players and validate the distribution."""
    print("Generating 230 players with tier tracking...")
    players, tier_map = generate_with_tier_tracking()
    print(f"Generated {len(players)} players\n")

    # === BATTING INTENT DISTRIBUTION ===
    print("=" * 50)
    print("BATTING INTENT DISTRIBUTION (Non-Bowlers)")
    print("=" * 50)

    non_bowlers = [p for p in players if p.role != PlayerRole.BOWLER]
    intent_counts = Counter(p.batting_intent for p in non_bowlers)
    total_non_bowlers = len(non_bowlers)

    target_distribution = {
        "accumulator": 50,
        "anchor": 25,
        "aggressive": 18,
        "power_hitter": 7,
    }

    print(f"\nTotal non-bowlers: {total_non_bowlers}")
    print(f"{'Intent':<15} {'Count':>6} {'Actual%':>8} {'Target%':>8} {'Status':<10}")
    print("-" * 50)

    for intent in ["accumulator", "anchor", "aggressive", "power_hitter"]:
        count = intent_counts.get(intent, 0)
        actual_pct = (count / total_non_bowlers * 100) if total_non_bowlers > 0 else 0
        target_pct = target_distribution[intent]
        diff = abs(actual_pct - target_pct)
        status = "OK" if diff < 8 else "WARN" if diff < 15 else "BAD"
        print(f"{intent:<15} {count:>6} {actual_pct:>7.1f}% {target_pct:>7}% {status:<10}")

    # === TRAIT DISTRIBUTION ===
    print("\n" + "=" * 50)
    print("TRAIT COUNT DISTRIBUTION")
    print("=" * 50)

    trait_count_dist = Counter()
    for p in players:
        traits = json.loads(p.traits) if p.traits else []
        trait_count_dist[len(traits)] += 1

    total = len(players)
    print(f"\n{'Traits':<10} {'Count':>6} {'Actual%':>8} {'Target%':>8}")
    print("-" * 40)

    # Overall target: ~55% no trait, ~35% one trait, ~10% two traits
    targets = {0: 55, 1: 35, 2: 10}
    for num in [0, 1, 2]:
        count = trait_count_dist.get(num, 0)
        actual_pct = (count / total * 100) if total > 0 else 0
        target_pct = targets[num]
        print(f"{num} traits   {count:>6} {actual_pct:>7.1f}% {target_pct:>7}%")

    # === INDIVIDUAL TRAIT DISTRIBUTION ===
    print("\n" + "=" * 50)
    print("INDIVIDUAL TRAIT DISTRIBUTION")
    print("=" * 50)

    trait_counts = Counter()
    traited_players = 0
    for p in players:
        traits = json.loads(p.traits) if p.traits else []
        if traits:
            traited_players += 1
            for t in traits:
                trait_counts[t] += 1

    print(f"\nPlayers with traits: {traited_players}/{len(players)} ({traited_players/len(players)*100:.1f}%)")
    print(f"\n{'Trait':<22} {'Count':>6}")
    print("-" * 30)

    for trait, count in trait_counts.most_common():
        print(f"{trait:<22} {count:>6}")

    # === CHOKER BY TIER ===
    print("\n" + "=" * 50)
    print("CHOKER DISTRIBUTION BY TIER (Actual Tiers)")
    print("=" * 50)

    # Use actual tier tracking from generation
    print(f"\n{'Tier':<10} {'Total':>6} {'Chokers':>8} {'Rate':>8} {'Expected':>10}")
    print("-" * 50)

    expected_rates = {"elite": "~3-5%", "star": "~8-12%", "good": "~12-18%", "solid": "~18-25%"}

    for tier in ["elite", "star", "good", "solid"]:
        tier_indices = [i for i, t in tier_map.items() if t == tier]
        tier_players = [players[i] for i in tier_indices]
        chokers = [p for p in tier_players if "choker" in (p.traits or "")]
        rate = (len(chokers) / len(tier_players) * 100) if tier_players else 0

        print(f"{tier:<10} {len(tier_players):>6} {len(chokers):>8} {rate:>7.1f}% {expected_rates[tier]:>10}")

    # === SPECIAL COMBOS ===
    print("\n" + "=" * 50)
    print("SPECIAL COMBINATIONS (Auction Highlights)")
    print("=" * 50)

    power_clutch = [p for p in players
                    if p.batting_intent == "power_hitter" and "clutch" in (p.traits or "")]
    finisher_batsmen = [p for p in players
                        if p.role == PlayerRole.BATSMAN and "finisher" in (p.traits or "")]
    partnership_breakers = [p for p in players
                            if p.role == PlayerRole.BOWLER and "partnership_breaker" in (p.traits or "")]

    print(f"\nPower Hitter + Clutch: {len(power_clutch)} players (should be 0-2)")
    for p in power_clutch:
        print(f"  - {p.name} (OVR: {p.overall_rating})")

    print(f"\nFinisher Batsmen: {len(finisher_batsmen)} players (target: ~6)")
    print(f"Partnership Breaker Bowlers: {len(partnership_breakers)} players (target: ~8)")

    # === ROLE BREAKDOWN ===
    print("\n" + "=" * 50)
    print("ROLE BREAKDOWN")
    print("=" * 50)

    role_counts = Counter(p.role.value for p in players)
    print(f"\n{'Role':<15} {'Count':>6}")
    print("-" * 25)
    for role, count in role_counts.most_common():
        print(f"{role:<15} {count:>6}")

    print("\n" + "=" * 50)
    print("VALIDATION COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    validate_distribution()
