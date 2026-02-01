# Player Balance Plan for Auction Pool

## Current State Analysis

### Batting Intent (Current)
Determined purely by stats - no control over distribution:
- **POWER_HITTER**: power >= 75 AND technique < 60
- **AGGRESSIVE**: power >= 65
- **ANCHOR**: technique >= 70
- **ACCUMULATOR**: default fallback

**Problem**: Distribution depends on random stat rolls, not intentional design.

### Traits (Current)
- 40% players: 0 traits
- 40% players: 1 trait
- 20% players: 2 traits
- All traits equally likely within role pool

**Problem**: Special traits like FINISHER and CLUTCH feel too common.

---

## Proposed Distribution (230 Players)

### Batting Intent Target Distribution

| Intent | Target % | Count | Rationale |
|--------|----------|-------|-----------|
| **ACCUMULATOR** | 50% | ~115 | Bread-and-butter players, most common |
| **ANCHOR** | 25% | ~58 | Valuable but not rare, stabilizers |
| **AGGRESSIVE** | 18% | ~41 | Impact players, somewhat special |
| **POWER_HITTER** | 7% | ~16 | Rare match-winners, highly valued |

**Note**: Bowlers remain ACCUMULATOR by default (they don't bat with intent).

### Trait Target Distribution

| Trait | Target % | Count | Rationale |
|-------|----------|-------|-----------|
| **No Trait** | 55% | ~127 | Most players are "normal" |
| **1 Trait** | 35% | ~80 | Some have one specialty |
| **2 Traits** | 10% | ~23 | Very rare elite mentality |

### Individual Trait Rarity (within trait pool)

| Trait | Rarity | % of Traited Players | Approx Count |
|-------|--------|---------------------|--------------|
| **CLUTCH** | Rare | 15% | ~15 players |
| **FINISHER** | Rare | 12% | ~12 players |
| **PARTNERSHIP_BREAKER** | Uncommon | 20% | ~20 players |
| **BUCKET_HANDS** | Common | 25% | ~25 players |
| **CHOKER** | Uncommon | 28% | ~28 players (negative trait) |

---

## Trait Distribution by Role

### Batsmen (30% of pool = ~69 players)
| Trait | Weight | Expected |
|-------|--------|----------|
| CLUTCH | 15 | ~4 players |
| FINISHER | 20 | ~6 players |
| CHOKER | 15 | ~4 players |
| No trait | 50 | ~35 players |

### Bowlers (35% of pool = ~80 players)
| Trait | Weight | Expected |
|-------|--------|----------|
| CLUTCH | 10 | ~3 players |
| PARTNERSHIP_BREAKER | 25 | ~8 players |
| CHOKER | 15 | ~5 players |
| No trait | 50 | ~40 players |

### All-Rounders (20% of pool = ~46 players)
| Trait | Weight | Expected |
|-------|--------|----------|
| CLUTCH | 15 | ~3 players |
| FINISHER | 15 | ~3 players |
| PARTNERSHIP_BREAKER | 15 | ~3 players |
| CHOKER | 10 | ~2 players |
| No trait | 45 | ~21 players |

### Wicket-Keepers (15% of pool = ~35 players)
| Trait | Weight | Expected |
|-------|--------|----------|
| CLUTCH | 15 | ~2 players |
| BUCKET_HANDS | 30 | ~5 players |
| CHOKER | 10 | ~2 players |
| No trait | 45 | ~16 players |

---

## Tier-Based Trait Probability

Higher tier players should have better chance of positive traits:

| Tier | No Trait | 1 Trait | 2 Traits | CHOKER Chance |
|------|----------|---------|----------|---------------|
| **Elite** | 30% | 50% | 20% | 5% (rare) |
| **Star** | 45% | 40% | 15% | 10% |
| **Good** | 55% | 35% | 10% | 15% |
| **Solid** | 65% | 30% | 5% | 20% |

**Logic**: Elite players are elite because they handle pressure (less CHOKER, more positive traits).

---

## Implementation Changes

### 1. New Constants in `player_generator.py`

```python
# Batting Intent Target Distribution (for non-bowlers)
BATTING_INTENT_WEIGHTS = {
    BattingIntent.ACCUMULATOR: 50,
    BattingIntent.ANCHOR: 25,
    BattingIntent.AGGRESSIVE: 18,
    BattingIntent.POWER_HITTER: 7,
}

# Trait count weights by tier
TRAIT_COUNT_WEIGHTS = {
    "elite": [30, 50, 20],   # [0, 1, 2 traits]
    "star": [45, 40, 15],
    "good": [55, 35, 10],
    "solid": [65, 30, 5],
}

# Trait weights by role (relative weights, not percentages)
TRAIT_WEIGHTS = {
    PlayerRole.BATSMAN: {
        PlayerTrait.CLUTCH: 15,
        PlayerTrait.FINISHER: 20,
        PlayerTrait.CHOKER: 15,
        None: 50,  # No trait
    },
    PlayerRole.BOWLER: {
        PlayerTrait.CLUTCH: 10,
        PlayerTrait.PARTNERSHIP_BREAKER: 25,
        PlayerTrait.CHOKER: 15,
        None: 50,
    },
    PlayerRole.ALL_ROUNDER: {
        PlayerTrait.CLUTCH: 15,
        PlayerTrait.FINISHER: 15,
        PlayerTrait.PARTNERSHIP_BREAKER: 15,
        PlayerTrait.CHOKER: 10,
        None: 45,
    },
    PlayerRole.WICKET_KEEPER: {
        PlayerTrait.CLUTCH: 15,
        PlayerTrait.BUCKET_HANDS: 30,
        PlayerTrait.CHOKER: 10,
        None: 45,
    },
}

# Reduce CHOKER chance for elite/star players
CHOKER_REDUCTION = {
    "elite": 0.25,  # 75% reduction
    "star": 0.5,    # 50% reduction
    "good": 0.75,   # 25% reduction
    "solid": 1.0,   # No reduction
}
```

### 2. New `_determine_batting_intent()` Method

```python
@classmethod
def _determine_batting_intent(cls, role: PlayerRole, power: int, technique: int) -> BattingIntent:
    """Assign batting intent with controlled distribution"""
    # Bowlers are always accumulators
    if role == PlayerRole.BOWLER:
        return BattingIntent.ACCUMULATOR

    # Use weighted random selection
    intents = list(cls.BATTING_INTENT_WEIGHTS.keys())
    weights = list(cls.BATTING_INTENT_WEIGHTS.values())

    selected = random.choices(intents, weights=weights)[0]

    # Validate: Power hitters need minimum power
    if selected == BattingIntent.POWER_HITTER and power < 60:
        return BattingIntent.AGGRESSIVE  # Downgrade if not powerful enough

    # Validate: Anchors need minimum technique
    if selected == BattingIntent.ANCHOR and technique < 50:
        return BattingIntent.ACCUMULATOR  # Downgrade if no technique

    return selected
```

### 3. New `_assign_traits()` Method

```python
@classmethod
def _assign_traits(cls, role: PlayerRole, tier: str) -> list[PlayerTrait]:
    """Assign traits with weighted probability based on role and tier"""
    # Determine number of traits
    count_weights = cls.TRAIT_COUNT_WEIGHTS.get(tier, [55, 35, 10])
    num_traits = random.choices([0, 1, 2], weights=count_weights)[0]

    if num_traits == 0:
        return []

    # Get trait weights for this role
    role_weights = cls.TRAIT_WEIGHTS.get(role, {})

    # Remove None and apply CHOKER reduction for higher tiers
    trait_pool = {}
    choker_mult = cls.CHOKER_REDUCTION.get(tier, 1.0)

    for trait, weight in role_weights.items():
        if trait is None:
            continue
        if trait == PlayerTrait.CHOKER:
            weight = int(weight * choker_mult)
        if weight > 0:
            trait_pool[trait] = weight

    if not trait_pool:
        return []

    # Select traits
    traits = []
    available = list(trait_pool.items())

    for _ in range(num_traits):
        if not available:
            break

        trait_list = [t for t, w in available]
        weight_list = [w for t, w in available]

        selected = random.choices(trait_list, weights=weight_list)[0]
        traits.append(selected)

        # Remove selected trait from pool (no duplicates)
        available = [(t, w) for t, w in available if t != selected]

    return traits
```

---

## New Traits to Consider (Future)

| Trait | Effect | Rarity |
|-------|--------|--------|
| **YORKER_SPECIALIST** | +15 bowling in death overs | Rare |
| **SPIN_KILLER** | +10 batting vs spin | Uncommon |
| **PACE_KILLER** | +10 batting vs pace | Uncommon |
| **ECONOMICAL** | -1 economy rate (bowling) | Uncommon |
| **STRIKE_ROTATOR** | +20% singles/doubles | Common |
| **DEATH_BOWLER** | +10 bowling in overs 16-20 | Rare |
| **POWERPLAY_SPECIALIST** | +10 in overs 1-6 | Uncommon |

---

## Validation Script

After implementing, run validation:

```python
# scripts/validate_player_balance.py
from collections import Counter

def validate_distribution(players):
    # Check batting intent distribution
    intents = Counter(p.batting_intent for p in players if p.role != 'bowler')
    print("Batting Intent Distribution:")
    for intent, count in intents.most_common():
        pct = count / sum(intents.values()) * 100
        print(f"  {intent}: {count} ({pct:.1f}%)")

    # Check trait distribution
    trait_counts = Counter()
    traited_players = 0
    for p in players:
        if p.traits:
            traited_players += 1
            for t in p.traits:
                trait_counts[t] += 1

    print(f"\nTraited Players: {traited_players}/{len(players)} ({traited_players/len(players)*100:.1f}%)")
    print("Trait Distribution:")
    for trait, count in trait_counts.most_common():
        print(f"  {trait}: {count}")
```

---

## Expected Auction Dynamics

With this balance:
1. **POWER_HITTER + CLUTCH** players will be EXTREMELY rare (~1-2 in pool) → bidding wars
2. **FINISHER** trait on good batsmen will be valuable (~12 total)
3. **PARTNERSHIP_BREAKER** bowlers will be sought after (~20 total)
4. **CHOKER** players will be bargains (negative trait, ~28 total)
5. Most players will be "solid but unremarkable" → filling squad spots
6. Elite players with 2 positive traits will be auction highlights

---

## Files to Modify

1. `/Users/rsumit123/work/willow-leather-api/app/generators/player_generator.py`
   - Add new constants
   - Rewrite `_determine_batting_intent()`
   - Rewrite trait assignment logic

2. `/Users/rsumit123/work/willow-leather-api/tests/test_player_generator.py`
   - Add distribution validation tests

3. `/Users/rsumit123/work/willow-leather-api/scripts/validate_player_balance.py` (new)
   - Script to verify distributions after generation
