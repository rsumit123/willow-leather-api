# Match Engine v2: "The Captain's Engine" — Full Specification

> **Status:** Draft — awaiting POC simulation results before API implementation.
> **Approach:** Simulation-first. Every number in this doc is a starting value. The POC will determine final calibration through 100+ match simulations.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Batter DNA](#2-batter-dna)
3. [Bowler DNA](#3-bowler-dna)
4. [Pitch DNA](#4-pitch-dna)
5. [Delivery System](#5-delivery-system)
6. [The Matchup Engine](#6-the-matchup-engine)
7. [Outcome Resolution](#7-outcome-resolution)
8. [Supporting Systems](#8-supporting-systems)
9. [Captain Decision Model](#9-captain-decision-model)
10. [Commentary Engine](#10-commentary-engine)
11. [Player Generation](#11-player-generation)
12. [POC Simulation Plan](#12-poc-simulation-plan)

---

## 1. Design Principles

### What Changes from v1

| v1 (Current) | v2 (New) |
|-------------|----------|
| `batting` vs `bowling` — single number contest | Granular DNA matchup — specific stats tested per delivery |
| Uniform random roll (`random.randint`) | Gaussian distribution (`random.gauss`) |
| Aggression is the only user choice | Bowling: delivery per ball + field per over. Batting: approach per over |
| Flat pitch modifier (+3/-2) | Pitch DNA with 5 attributes + deterioration |
| Static bowler effectiveness | Fatigue degrades stats over 4 overs + ball age affects swing/spin |
| Generic commentary ("FOUR!") | Structured ball data → template-based rich commentary |
| Run rate governors dominate outcomes | Skill matchups dominate; governors are a light safety net |

### Core Rules

1. **Skill is Gaussian.** Players perform near their mean. Wild results require extreme matchups or high-risk mode.
2. **Every delivery tests specific attributes.** A bouncer tests different batter skills than a yorker. The captain exploits this.
3. **Bowler execution is not guaranteed.** Control stat determines if the bowler lands the intended delivery. Miss = loose ball.
4. **No hard governors.** Outcomes emerge from the matchup math. Safety nets exist but are subtle (+/- 5-8 range, not +/- 30-40 like v1).
5. **Captain decisions matter ~15-25%.** Enough to feel smart, not enough to override player quality.

---

## 2. Batter DNA

Every batter has **7 attributes** on a 0-100 scale. Each maps to specific deliveries that test it.

| Attribute | What It Represents | Tested By |
|-----------|-------------------|-----------|
| `vs_pace` | Ability against swing, seam, full-length pace | Outswingers, inswingers, good length pace |
| `vs_bounce` | Ability against short balls, rising deliveries | Bouncers, short-of-length pace |
| `vs_spin` | Ability against turning deliveries | Stock spin, flighted spin |
| `vs_deception` | Reading variations, handling surprises | Googlies, slower balls, arm balls, knuckle balls |
| `off_side` | Proficiency scoring through off-side (cover, point, third man) | Any delivery on off-stump or outside off |
| `leg_side` | Proficiency scoring through leg-side (mid-wicket, square leg, fine leg) | Any delivery on leg-stump or at the body |
| `power` | Six-hitting ability, boundary clearing distance | Determines if good contact = 4 or 6. Not tested directly. |

### Why 7 and Not 9 or 13

- Each attribute creates a **unique matchup axis.** A bouncer tests `vs_bounce`; an outswinger tests `vs_pace`. Different tactical choices.
- 7 is displayable on a mobile screen as a compact radar chart or stat bar.
- 7 is generatable with meaningful variation across 230 players.
- Merging further (e.g., `vs_pace` + `vs_bounce` into one) loses the bouncer vs. swing distinction, which is a core captaincy decision.

### Attribute Interactions

- `off_side` and `leg_side` are **secondary modifiers**, not primary. They determine *where* the runs go, not *if* the batter survives.
- `power` only matters on positive-margin contact. A power hitter who gets beaten still gets beaten.
- `vs_deception` is cross-type — it applies to both spin variations AND pace slower balls.

---

## 3. Bowler DNA

Bowlers have **type-specific attributes**. This means a pacer and a spinner have different stat profiles.

### Pacer Attributes

| Attribute | Range | What It Does |
|-----------|-------|-------------|
| `speed` | 120-155 (kph) | Reduces batter reaction time. Amplifies `vs_pace` and `vs_bounce` tests. |
| `swing` | 0-100 | Lateral air movement. Primary weapon for outswingers/inswingers. |
| `bounce` | 0-100 | Vertical extraction from the pitch. Primary weapon for bouncers. |
| `control` | 0-100 | Probability of executing intended delivery. Universal. |

### Spinner Attributes

| Attribute | Range | What It Does |
|-----------|-------|-------------|
| `turn` | 0-100 | Lateral movement off the pitch. Primary weapon for stock deliveries. |
| `flight` | 0-100 | Deception in the air, loop, drift. Creates mistiming. |
| `variation` | 0-100 | Quality of mystery balls (googly, doosra, carrom ball). |
| `control` | 0-100 | Probability of executing intended delivery. Universal. |

### Medium Pacers

Use the **pacer attribute set** but with:
- `speed`: 125-140 range (capped lower)
- `swing`: typically higher relative to speed (they rely on movement, not pace)
- `bounce`: typically lower (less extraction)

### Bowling Type Mapping (from v1)

| v1 BowlingType | v2 DNA Set | Speed Range |
|----------------|-----------|-------------|
| `PACE` | Pacer | 140-155 |
| `MEDIUM` | Pacer (reduced) | 125-140 |
| `OFF_SPIN` | Spinner | N/A |
| `LEG_SPIN` | Spinner | N/A |
| `LEFT_ARM_SPIN` | Spinner | N/A |

---

## 4. Pitch DNA

Every match has a pitch with **5 attributes** (0-100 scale).

| Attribute | What It Does |
|-----------|-------------|
| `pace_assist` | Amplifies pacer effectiveness (speed, swing, bounce all benefit) |
| `spin_assist` | Amplifies spinner effectiveness (turn, flight benefit) |
| `bounce` | Vertical bounce level. High = bouncers effective, sweep harder. Low = sweep easier, bouncers harmless. |
| `carry` | How well edges travel to keeper/slips. Affects catch probability in edge zone. |
| `deterioration` | How much pitch degrades per innings. High = spin becomes dominant, batting gets harder. |

### Pitch Types (Presets)

| Pitch | pace_assist | spin_assist | bounce | carry | deterioration | Character |
|-------|-------------|-------------|--------|-------|---------------|-----------|
| **Green Seamer** | 80 | 15 | 70 | 85 | 25 | Pace heaven. Bowl first. |
| **Dust Bowl** | 20 | 85 | 35 | 45 | 80 | Spin nightmare. Deteriorates fast. |
| **Flat Deck** | 40 | 35 | 55 | 60 | 20 | Road. Bat first, big scores. |
| **Bouncy Track** | 75 | 20 | 90 | 85 | 20 | Express pace + bounce. Intimidating. |
| **Slow Turner** | 30 | 60 | 40 | 50 | 55 | Spin from ball one. Gets worse. |
| **Balanced** | 55 | 45 | 60 | 65 | 35 | Fair for both. Standard. |

### How Pitch Modifies Bowler Stats

```python
# Pitch amplifies or dampens bowler attributes
# Range: 0.5x (pitch_assist=0) to 1.5x (pitch_assist=100)
def apply_pitch(stat, pitch_assist):
    return stat * (0.5 + pitch_assist * 0.01)

# Examples:
# Spinner turn=70 on dust bowl (spin_assist=85): 70 * 1.35 = 94.5
# Spinner turn=70 on green seamer (spin_assist=15): 70 * 0.65 = 45.5
# Pacer swing=80 on green seamer (pace_assist=80): 80 * 1.30 = 104 (capped at 100 effective)
```

### Pitch Deterioration

The pitch changes between innings (and could change within an innings for longer formats):

```python
# Second innings modifier for spin
spin_assist_2nd = pitch.spin_assist * (1.0 + pitch.deterioration / 200)

# Dust bowl (deterioration=80): spin_assist goes from 85 → 85 * 1.4 = 119 (capped 100)
# Flat deck (deterioration=20): spin_assist goes from 35 → 35 * 1.1 = 38.5 (barely changes)
```

This means:
- On deteriorating pitches, batting first is a significant advantage.
- Spinner effectiveness increases naturally in the second innings.
- The user sees the pitch info and factors it into toss decisions.

---

## 5. Delivery System

Each bowler has a **repertoire** of 4-5 deliveries based on their type and DNA. Every delivery defines:
- Which bowler stats it uses (weighted)
- Which batter stats it tests (weighted)
- Base execution difficulty (higher = harder to land, Control is tested against this)
- Risk profile (affects variance on success/failure)

### Pacer Deliveries

| Delivery | Available When | Bowler Stat Weights | Batter Stat Weights | Exec. Difficulty | Notes |
|----------|---------------|-------------------|-------------------|-----------------|-------|
| **Good Length** | Always | control 0.4, swing 0.3, speed 0.3 | vs_pace 0.7, off_side 0.3 | 30 | Bread and butter. Safe. |
| **Outswinger** | swing >= 40 | swing 0.6, control 0.4 | vs_pace 0.6, off_side 0.4 | 42 | Edge-creating. Tests front foot. |
| **Inswinger** | swing >= 40 | swing 0.6, control 0.4 | vs_pace 0.5, leg_side 0.5 | 45 | LBW/bowled chance. |
| **Bouncer** | bounce >= 40 | bounce 0.5, speed 0.5 | vs_bounce 0.6, leg_side 0.4 | 38 | Short ball. Tests back foot play. |
| **Yorker** | Always | control 0.7, speed 0.3 | vs_pace 0.3, power 0.3, leg_side 0.4 | 58 | Hard to execute. Deadly when landed. |
| **Slower Ball** | Always | control 0.5, speed 0.5 | vs_deception 0.7, power 0.3 | 48 | Change of pace. Surprise weapon. |
| **Wide Yorker** | control >= 55 | control 0.7, speed 0.3 | vs_pace 0.3, off_side 0.7 | 55 | Death overs weapon. High dot ball chance. |

### Spinner Deliveries

| Delivery | Available When | Bowler Stat Weights | Batter Stat Weights | Exec. Difficulty | Notes |
|----------|---------------|-------------------|-------------------|-----------------|-------|
| **Stock Ball** | Always | turn 0.5, control 0.5 | vs_spin 0.7, off_side 0.3 | 28 | Consistent. Relies on turn. |
| **Flighted** | flight >= 40 | flight 0.6, turn 0.4 | vs_spin 0.4, vs_deception 0.3, power 0.3 | 40 | Loopy. Invites drive. Stumping chance. |
| **Arm Ball / Googly** | variation >= 45 | variation 0.7, control 0.3 | vs_deception 0.8, vs_spin 0.2 | 52 | Surprise ball. High reward if landed. |
| **Flat & Quick** | Always | control 0.7, turn 0.3 | power 0.5, vs_spin 0.5 | 32 | Defensive. Hard to score, hard to get out. |
| **Wide of Off** | control >= 50 | control 0.6, turn 0.4 | off_side 0.6, vs_spin 0.4 | 38 | Creates doubt. Dot ball weapon. |

### Delivery Availability

A bowler's repertoire is determined at generation time based on their DNA. The UI shows only the deliveries this bowler can execute.

```python
def get_repertoire(bowler):
    deliveries = ["good_length"]  # Always available (pacer) or "stock_ball" (spinner)

    if bowler.is_pacer:
        if bowler.swing >= 40:
            deliveries += ["outswinger", "inswinger"]
        if bowler.bounce >= 40:
            deliveries.append("bouncer")
        deliveries.append("yorker")      # Always, but hard to execute
        deliveries.append("slower_ball")  # Always
        if bowler.control >= 55:
            deliveries.append("wide_yorker")

    if bowler.is_spinner:
        if bowler.flight >= 40:
            deliveries.append("flighted")
        if bowler.variation >= 45:
            deliveries.append("arm_ball")  # or googly based on spin type
        deliveries.append("flat_quick")   # Always
        if bowler.control >= 50:
            deliveries.append("wide_of_off")

    return deliveries
```

### No Phase Locks

Every delivery is available in every over. But **execution difficulty is modified by conditions:**

```python
# Phase modifier on execution difficulty
phase_mods = {
    "powerplay": {"yorker": +5, "bouncer": -3, "outswinger": -5},  # New ball helps swing, yorker harder
    "middle":    {},                                                  # No modifier
    "death":     {"yorker": -5, "slower_ball": -3, "bouncer": +3},   # Old ball = yorkers easier
}

# Ball age modifier on bowler stats
def ball_age_modifier(overs_bowled, stat_name):
    if stat_name == "swing":
        if overs_bowled <= 6: return 1.0      # New ball, full swing
        if overs_bowled <= 12: return 0.65     # Swing fading
        return 0.40                             # Old ball, minimal swing
    if stat_name == "turn":
        if overs_bowled <= 6: return 0.85      # New ball, less grip
        if overs_bowled <= 12: return 1.0       # Ball roughing up
        return 1.15                             # Old ball, grips and turns
    return 1.0  # speed, bounce, control unaffected by ball age
```

---

## 6. The Matchup Engine

This is the core calculation that replaces v1's margin system. Every ball goes through this pipeline.

### Step 1: Execution Check

The bowler attempts to land their chosen delivery. Their `control` stat is tested.

```python
def execution_check(bowler, delivery, pitch, fatigue_mod, overs_bowled):
    effective_control = bowler.control * fatigue_mod

    execution_roll = random.gauss(effective_control, 8)

    target = delivery.exec_difficulty
    target += phase_modifier(overs_bowled, delivery.name)
    target += pitch_difficulty_mod(pitch, delivery)  # Some pitches make certain deliveries harder

    if execution_roll >= target:
        return "executed"           # Bowler lands it as intended

    miss_degree = target - execution_roll
    if miss_degree > 15:
        return "bad_miss"           # Full toss, long hop — free hit for batter
    else:
        return "slight_miss"        # Half-volley, slightly short — easier for batter
```

**On execution failure:**
- `bad_miss`: Batter gets a significant bonus (+15-20 to their margin). Almost always runs.
- `slight_miss`: Batter gets a moderate bonus (+5-10). Easier ball but still contestable.
- `executed`: Full matchup calculation applies.

### Step 2: Calculate Bowler Attack Rating

How dangerous this delivery is, considering bowler skill + pitch + ball age.

```python
def bowler_attack(bowler, delivery, pitch, overs_bowled, fatigue_mod):
    rating = 0
    for stat_name, weight in delivery.bowler_weights.items():
        base_stat = getattr(bowler, stat_name)

        # Apply pitch modifier
        pitch_assist = get_pitch_assist(pitch, stat_name)  # maps stat to relevant pitch attribute
        effective_stat = base_stat * (0.5 + pitch_assist * 0.01)

        # Apply ball age
        effective_stat *= ball_age_modifier(overs_bowled, stat_name)

        # Apply fatigue
        effective_stat *= fatigue_mod

        # Cap at 100
        effective_stat = min(100, effective_stat)

        rating += effective_stat * weight

    return rating
```

### Step 3: Calculate Batter Skill Rating

How well-equipped the batter is to handle this specific delivery.

```python
def batter_skill(batter, delivery):
    rating = 0
    for stat_name, weight in delivery.batter_weights.items():
        stat = getattr(batter, stat_name)
        rating += stat * weight
    return rating
```

### Step 4: Tactical Bonus

How well the captain's choice exploits or mismatches the batter.

```python
def tactical_bonus(batter, delivery):
    # Primary tested stat is the one with highest weight
    primary_stat_name = max(delivery.batter_weights, key=delivery.batter_weights.get)
    primary_stat_value = getattr(batter, primary_stat_name)

    # Exploiting weakness (stat < 50) gives positive bonus
    # Attacking strength (stat > 50) gives negative bonus
    # Range: -15 to +15
    bonus = (50 - primary_stat_value) * 0.3

    return bonus
```

### Step 5: The Gaussian Roll

```python
def calculate_margin(bowler_attack, batter_skill, tactical_bonus, batting_approach, sigma):
    # Batting approach modifiers
    approach_mods = {
        "survive":   {"sigma_mult": 0.7, "base_shift": +5},   # Tight, defensive
        "rotate":    {"sigma_mult": 0.9, "base_shift": +2},   # Slightly conservative
        "push":      {"sigma_mult": 1.1, "base_shift": -2},   # Slightly aggressive
        "all_out":   {"sigma_mult": 1.4, "base_shift": -6},   # Wild variance
    }

    mod = approach_mods.get(batting_approach, approach_mods["rotate"])

    adjusted_sigma = sigma * mod["sigma_mult"]
    batter_performance = random.gauss(batter_skill + mod["base_shift"], adjusted_sigma)

    difficulty = bowler_attack + tactical_bonus

    margin = batter_performance - difficulty
    return margin
```

### Step 6: Full Pipeline

```python
def simulate_ball(bowler, batter, delivery, pitch, innings_state, batting_approach):
    overs_bowled = innings_state.overs
    fatigue = get_fatigue_modifier(bowler, innings_state)

    # Phase-based sigma
    if overs_bowled < 6:
        sigma = 12      # Powerplay: moderate variance
    elif overs_bowled < 16:
        sigma = 10      # Middle: skill dominates
    else:
        sigma = 14      # Death: high variance, boom or bust

    # Step 1: Execution
    exec_result = execution_check(bowler, delivery, pitch, fatigue, overs_bowled)

    if exec_result == "bad_miss":
        batter_bonus = random.randint(15, 22)
    elif exec_result == "slight_miss":
        batter_bonus = random.randint(5, 12)
    else:
        batter_bonus = 0

    # Step 2: Bowler attack rating
    attack = bowler_attack(bowler, delivery, pitch, overs_bowled, fatigue)

    # Step 3: Batter skill rating
    skill = batter_skill(batter, delivery) + batter_bonus

    # Step 4: Tactical bonus
    tac_bonus = tactical_bonus(batter, delivery)

    # Step 5: Gaussian margin
    margin = calculate_margin(attack, skill, tac_bonus, batting_approach, sigma)

    # Step 6: Resolve outcome
    return resolve_outcome(margin, batter, delivery, pitch, innings_state)
```

---

## 7. Outcome Resolution

The margin from Step 6 maps to ball outcomes. Two stages: **contact quality**, then **distance/trajectory**.

### Contact Quality (from Margin)

| Margin Range | Contact Quality | Description |
|-------------|----------------|-------------|
| >= 25 | `perfect` | Middled, full power available |
| 15 to 24 | `good` | Well-timed, clean contact |
| 5 to 14 | `decent` | Reasonable contact, less power |
| -5 to 4 | `defended` | Blocked, pushed, dead bat |
| -12 to -6 | `beaten` | Play and miss, bowler wins |
| -20 to -13 | `edge` | Edge to keeper/slips area. Catch chance. |
| <= -21 | `clean_beat` | Through the gate. High wicket probability. |

### Distance Calculation (for positive contact)

Power determines how far the ball travels when contact is good.

```python
def calculate_distance(margin, power, contact):
    if contact in ["defended", "beaten", "edge", "clean_beat"]:
        return 0  # No meaningful hit

    # Base distance from timing quality
    if contact == "perfect":
        base = 45 + (margin - 25) * 1.2
    elif contact == "good":
        base = 30 + (margin - 15) * 1.5
    elif contact == "decent":
        base = 15 + (margin - 5) * 1.5

    # Power bonus (0-100 mapped to 0-35m extra distance)
    power_bonus = power * 0.35

    # Some randomness in placement
    distance = base + power_bonus + random.gauss(0, 5)

    return max(0, distance)
```

### Runs from Distance

| Distance | Result |
|----------|--------|
| >= 75m | **SIX** (clears the rope) |
| 65-74m | **FOUR** (beats the field, reaches boundary) |
| 45-64m | 2-3 runs (in the gap, good running) |
| 20-44m | 1-2 runs (placed into a gap) |
| 0-19m | 0-1 runs (to a fielder, possible single) |

### Edge Zone Resolution

When contact quality is `edge` (margin -20 to -13):

```python
def resolve_edge(pitch, field_template):
    # Carry determines if edge reaches fielders
    carry_factor = pitch.carry / 100  # 0.0 to 1.0

    # Field template affects catch probability
    catch_base = field_template.catch_modifier  # e.g., +15% for aggressive, -10% for defensive

    # Base catch chance: 20%
    catch_chance = 0.20 * carry_factor + (catch_base / 100)
    catch_chance = max(0.05, min(0.50, catch_chance))  # Clamp 5%-50%

    if random.random() < catch_chance:
        return "caught"  # WICKET
    else:
        # Edge runs through/drops short
        return random.choice([0, 0, 1, 1])  # Mostly dots, occasional single
```

### Clean Beat Resolution

When contact quality is `clean_beat` (margin <= -21):

```python
def resolve_clean_beat(margin, delivery):
    margin_abs = abs(margin)

    # Wicket probability scales with how badly beaten
    # margin -21: 55% wicket chance
    # margin -30: 80% wicket chance
    # margin -40+: 95% wicket chance
    wicket_chance = min(0.95, 0.55 + (margin_abs - 21) * 0.03)

    if random.random() < wicket_chance:
        # Determine dismissal type based on delivery
        return get_dismissal_type(delivery)
    else:
        # Survived somehow — ball missed everything
        return 0  # Dot ball
```

### Dismissal Types by Delivery

| Delivery | Primary Dismissal | Secondary Dismissal |
|----------|------------------|-------------------|
| Outswinger | caught_behind (50%) | caught_slip (30%), bowled (20%) |
| Inswinger | lbw (45%) | bowled (40%), caught (15%) |
| Bouncer | caught (60%) | top_edge_caught (30%), hit_wicket (10%) |
| Yorker | bowled (55%) | lbw (35%), caught (10%) |
| Stock spin | stumped (30%) | bowled (30%), caught (25%), lbw (15%) |
| Flighted spin | stumped (40%) | caught (35%), bowled (15%), lbw (10%) |
| Googly/Arm ball | bowled (45%) | lbw (35%), stumped (10%), caught (10%) |
| Slower ball | caught (55%) | bowled (25%), lbw (20%) |

---

## 8. Supporting Systems

### 8.1 Fatigue

Bowler effectiveness drops with each over bowled in the match.

```python
FATIGUE_MULTIPLIERS = {
    1: 1.00,   # Over 1: fresh
    2: 0.97,   # Over 2: minimal drop
    3: 0.92,   # Over 3: noticeable
    4: 0.85,   # Over 4: significant
}

def get_fatigue_modifier(bowler, innings_state):
    spell = innings_state.bowler_spells.get(bowler.id)
    if not spell:
        return 1.0

    overs_bowled = spell.overs + (1 if spell.balls > 0 else 0)
    return FATIGUE_MULTIPLIERS.get(overs_bowled, 0.85)
```

**Implications for captain:**
- Use your best bowler in overs 1-2 (fresh, maximum impact)?
- Or save them for overs 18-20 (when the match is decided, but they're on over 3-4)?
- Your 5th/6th bowling option (part-timer) is fresh when main bowlers are tired.

### 8.2 Ball Age

The ball changes character over 20 overs. This affects bowler stat effectiveness.

| Overs | Swing Effect | Bounce Effect | Spin Effect | Character |
|-------|-------------|--------------|------------|-----------|
| 1-6 | 100% | 100% | 85% | New ball. Swing bowlers peak. |
| 7-12 | 65% | 95% | 100% | Swing fading. Ball roughing up. |
| 13-20 | 40% | 90% | 115% | Old ball. Spin grips. Cutters work. |

**Implications:**
- Open with swing bowlers while ball is new (overs 1-6).
- Bring spinners in middle overs when ball grips (7-12).
- Death overs: pace yorkers work regardless of ball age (speed/control matter, not swing).

### 8.3 Batter Settling In

New batters are vulnerable. Settled batters are harder to dismiss.

```python
def settled_modifier(balls_faced):
    if balls_faced <= 5:
        return -5      # New batter: slight disadvantage
    elif balls_faced <= 15:
        return 0       # Adjusting: neutral
    elif balls_faced <= 40:
        return +3      # Settled: slight advantage
    else:
        return +5      # Well set: noticeable advantage
```

This is added to the batter's skill rating in the margin calculation.

### 8.4 Extras

Unchanged from v1, with minor adjustments:

```python
def check_extras(bowler, fatigue_mod):
    roll = random.random()
    effective_control = bowler.control * fatigue_mod

    # Wide probability: inversely related to control
    # High control (85+): ~1% wide rate
    # Low control (50): ~3% wide rate
    wide_chance = 0.04 - (effective_control * 0.0003)
    wide_chance = max(0.005, min(0.04, wide_chance))

    if roll < wide_chance:
        return "wide"

    # No-ball: flat 0.5% (yep, some things stay simple)
    if roll < wide_chance + 0.005:
        return "no_ball"

    return None
```

### 8.5 Light Safety Net (Replaces Heavy Governors)

v1 used +/- 30-40 adjustments to force scores into range. v2 uses a **subtle nudge** that only activates in extreme cases.

```python
def safety_net(innings_state):
    """
    Light safety net. Only activates when things are truly extreme.
    Max adjustment: +/- 8 (compared to v1's +/- 40).
    """
    total_balls = innings_state.overs * 6 + innings_state.balls
    if total_balls < 18:  # No adjustment in first 3 overs
        return 0

    current_rr = innings_state.run_rate

    # Floor: prevent sub-40 scores (extremely rare in T20)
    if current_rr < 2.0 and innings_state.wickets < 8:
        return +8  # Gentle boost

    # Ceiling: prevent 300+ scores (impossible in T20)
    if current_rr > 15:
        return -8  # Gentle cap

    return 0
```

The key difference: in v2, **realistic scores emerge from the matchup math itself**, not from artificial governors. The safety net is a 1-in-50-match backstop, not a per-ball crutch.

---

## 9. Captain Decision Model

### When Bowling (Per Over + Per Ball)

**Per Over:**
1. Select bowler (see repertoire, fatigue, matchup preview)
2. Select field template (7-8 options, some restricted by powerplay)

**Per Ball:**
3. Select delivery from bowler's repertoire (4-5 buttons)

**Decision flow:**
```
Over start → See batter DNA summary (weaknesses highlighted)
           → Pick bowler (see which deliveries they unlock)
           → Pick field template

Ball 1     → Pick delivery → See result + commentary
Ball 2     → Pick delivery (react to ball 1) → See result + commentary
...
Ball 6     → Over summary → Next over decisions
```

### When Batting (Per Over)

**Per Over:**
1. Select batting approach: `survive` / `rotate` / `push` / `all_out`
2. (On wicket fall) Select next batter from remaining order

**Situational popups (not every over):**
- Weak batter vs strong bowler detected: "Danger matchup. Switch to survive?"
- Required rate climbing: "Need 12 per over. Switch to push?"

**Decision flow:**
```
Over start → See bowler DNA summary
           → Pick approach (one tap)

Ball 1-6   → Watch auto-play + commentary (tap to advance or auto-advance)
           → If wicket: pick next batter

Over end   → Summary → Adjust approach for next over
```

### Field Templates

| Template | Catch Mod | Boundary Save | Dot Ball Mod | Powerplay? |
|----------|-----------|--------------|-------------|-----------|
| **Aggressive** | +15% | -10% | 0% | Yes |
| **Slip Cordon** | +20% (edges) | -15% | -5% | Yes (ideal) |
| **Spin Web** | +12% (close) | -8% | +5% | Yes |
| **Balanced** | 0% | 0% | 0% | Yes |
| **Offside Heavy** | +5% | +5% off | +8% vs off | Yes |
| **Legside Heavy** | +5% | +5% leg | +8% vs leg | Yes |
| **Defensive Spread** | -10% | +15% | +5% | Yes |
| **Death Protect** | -5% | +20% | 0% | No (needs boundary riders) |

**Powerplay restriction (overs 1-6):** Max 2 fielders outside 30-yard circle. Templates that require more than 2 outside are unavailable.

### Scoring Zone Interaction

When the batting captain sets an approach, the batter's **zone preference** is determined by their DNA (strongest side). But field templates counter this:

```python
def zone_adjustment(batter, field_template):
    # Batter naturally plays to their stronger side
    if batter.off_side > batter.leg_side:
        preferred_zone = "offside"
    else:
        preferred_zone = "legside"

    # If field is loaded on batter's preferred side, runs are harder to come by
    if field_template.heavy_side == preferred_zone:
        return -3  # Batter's scoring options restricted
    elif field_template.heavy_side and field_template.heavy_side != preferred_zone:
        return +2  # Field on wrong side, batter finds gaps

    return 0
```

---

## 10. Commentary Engine

### Structured Ball Data

Every ball produces a rich data object:

```python
@dataclass
class BallData:
    ball_number: str          # "8.3"
    bowler_name: str
    batter_name: str

    # Delivery info
    delivery_type: str        # "bouncer", "outswinger", etc.
    delivery_executed: bool   # Did control check pass?
    speed_kph: int            # For pace bowlers
    line: str                 # "off_stump", "middle", "leg_stump", "wide_off", "at_body"
    length: str               # "short", "good_length", "full", "yorker", "half_volley"

    # Contact info
    contact_quality: str      # "perfect", "good", "decent", "defended", "beaten", "edge", "clean_beat"
    shot_type: str            # "drive", "pull", "cut", "sweep", "defense", "leave", etc.

    # Result
    runs: int
    is_wicket: bool
    is_boundary: bool
    is_six: bool
    dismissal_type: str       # "bowled", "caught", "lbw", etc.
    fielder_name: str         # If caught

    # Generated
    commentary: str
```

### Shot Type Selection

The shot played depends on the delivery type + batter DNA:

```python
SHOT_MAP = {
    "bouncer": {
        "high_vs_bounce": ["pull", "hook", "upper_cut"],        # Good batter
        "low_vs_bounce":  ["fend", "duck", "top_edge_pull"],    # Struggling batter
    },
    "outswinger": {
        "high_vs_pace": ["drive_cover", "punch_off", "leave"],
        "low_vs_pace":  ["edge_drive", "poke", "fish_outside"],
    },
    "yorker": {
        "high_vs_pace": ["dig_out", "flick", "drive_straight"],
        "low_vs_pace":  ["yorked", "jam_down", "squeeze"],
    },
    "stock_spin": {
        "high_vs_spin": ["drive", "sweep", "work_leg"],
        "low_vs_spin":  ["pad_up", "inside_edge", "beaten_turn"],
    },
    "flighted": {
        "high_vs_spin": ["lofted_drive", "sweep", "advance_drive"],
        "low_vs_spin":  ["stumped_attempt", "miscue", "beaten_flight"],
    },
    # ... more mappings
}
```

### Commentary Templates

Templates are categorized by: `delivery_type` x `contact_quality` x `result`. Each category has 3-5 variations.

**Example template set for `bouncer` + `edge` + `caught`:**

```python
TEMPLATES["bouncer"]["edge"]["caught"] = [
    "SHORT from {bowler} at {speed}kph! {batter} goes for the pull but it takes the top edge, "
    "ballooning towards {fielder_position}. {fielder} settles under it. Gone!",

    "Banged in short by {bowler}! {batter} tries to fend but the extra bounce does the trick. "
    "Gloves it through to {fielder} behind the stumps.",

    "{speed}kph bouncer, rising sharply! {batter} attempts the hook but gets a thin edge. "
    "{fielder} at {fielder_position} takes a smart catch.",
]
```

**Example for `outswinger` + `defended` + `dot`:**

```python
TEMPLATES["outswinger"]["defended"]["dot"] = [
    "Full and swinging away. {batter} drives but finds the ball move late. "
    "Plays and misses outside off. Good bowling.",

    "Lovely outswinger from {bowler}, shaping away from {batter}. "
    "Left alone outside off stump. Dot ball.",

    "Good length from {bowler}, nibbling away. {batter} shoulders arms. "
    "That's the channel to be bowling.",
]
```

**Template count estimate:**
- 12 delivery types x 7 contact qualities x ~3 result types = ~250 categories
- 3 variations each = ~750 template strings
- Context additions (milestones, pressure, partnerships) = +100 templates
- **Total: ~850 templates** (manageable, can start with ~300 for POC)

### Line and Length Generation

Based on delivery type, with some randomness:

```python
DELIVERY_LINES = {
    "outswinger": ["off_stump", "off_stump", "wide_off", "off_stump"],
    "inswinger": ["middle", "leg_stump", "middle", "off_stump"],
    "bouncer": ["at_body", "off_stump", "at_body", "leg_stump"],
    "yorker": ["leg_stump", "middle", "off_stump", "leg_stump"],
    "good_length": ["off_stump", "off_stump", "middle", "off_stump"],
    "stock_spin": ["off_stump", "middle", "off_stump", "leg_stump"],
    "flighted": ["off_stump", "off_stump", "middle"],
    # etc.
}

DELIVERY_LENGTHS = {
    "outswinger": ["good_length", "full", "good_length"],
    "bouncer": ["short", "short", "short_of_length"],
    "yorker": ["yorker", "yorker", "full"],  # slight_miss → full instead of yorker
    # etc.
}
```

---

## 11. Player Generation

### Attribute Generation by Role and Tier

#### Batsman

| Attribute | Elite (base 80-90) | Star (70-80) | Good (62-72) | Solid (58-65) |
|-----------|-------------------|-------------|-------------|--------------|
| vs_pace | base+5 ±10 | base+5 ±10 | base ±12 | base ±12 |
| vs_bounce | base ±12 | base ±12 | base-5 ±12 | base-5 ±15 |
| vs_spin | base ±12 | base-5 ±12 | base-5 ±12 | base-8 ±15 |
| vs_deception | base-5 ±15 | base-8 ±15 | base-10 ±15 | base-12 ±15 |
| off_side | base ±12 | base ±12 | base-3 ±12 | base-5 ±12 |
| leg_side | base ±12 | base ±12 | base-3 ±12 | base-5 ±12 |
| power | base-5 ±15 | base-5 ±15 | base-8 ±15 | base-10 ±15 |

#### Bowler (Batting DNA — Low)

All batter stats generated with `base = 25-35 ± 10`. Bowlers are not meant to bat well.

#### Bowler (Bowling DNA)

**Pacer:**

| Attribute | Elite | Star | Good | Solid |
|-----------|-------|------|------|-------|
| speed | 143-153 | 138-148 | 133-143 | 128-138 |
| swing | base ±15 | base-5 ±15 | base-8 ±15 | base-10 ±15 |
| bounce | base ±15 | base-5 ±15 | base-8 ±15 | base-10 ±15 |
| control | base+5 ±10 | base ±12 | base-3 ±12 | base-5 ±12 |

**Spinner:**

| Attribute | Elite | Star | Good | Solid |
|-----------|-------|------|------|-------|
| turn | base+5 ±12 | base ±12 | base-3 ±12 | base-5 ±15 |
| flight | base ±15 | base-5 ±15 | base-8 ±15 | base-10 ±15 |
| variation | base ±15 | base-5 ±15 | base-8 ±15 | base-10 ±15 |
| control | base+5 ±10 | base ±12 | base-3 ±12 | base-5 ±12 |

#### All-Rounder

Both batting DNA and bowling DNA generated at `base - 5` (jack of all trades, master of neither).

#### Wicket-Keeper

Batting DNA at `base - 3`. Bowling DNA minimal. Fielding stats (not in match engine, but for squad value) boosted.

### Weakness Generation

**Critical rule:** Every batter gets **1-2 weak attributes** that are **15-25 points below their average**. This creates matchup diversity.

```python
def apply_weakness(attributes: dict, num_weaknesses: int = None):
    if num_weaknesses is None:
        num_weaknesses = random.choices([1, 2], weights=[60, 40])[0]

    # Exclude power from weakness candidates (it's a secondary stat)
    weakness_candidates = ["vs_pace", "vs_bounce", "vs_spin", "vs_deception", "off_side", "leg_side"]

    weak_stats = random.sample(weakness_candidates, num_weaknesses)

    avg = sum(attributes[s] for s in weakness_candidates) / len(weakness_candidates)

    for stat in weak_stats:
        reduction = random.randint(15, 25)
        attributes[stat] = max(10, int(avg - reduction))

    return attributes, weak_stats
```

**Why this matters:** Without weaknesses, every elite batter is equally good against everything. With weaknesses, an elite batter might have `vs_pace: 88, vs_spin: 85, vs_bounce: 55`. The captain sees that weakness and picks a bouncer plan. That's the whole game.

### Trait System (Expanded from v1)

New traits that interact with the matchup system:

| Trait | Type | Effect | Who Gets It |
|-------|------|--------|------------|
| `CLUTCH` | Batter/Bowler | +8 to skill/attack in pressure | Rare (8 weight) |
| `CHOKER` | Batter/Bowler | -12 to skill/attack in pressure | Common for low tiers |
| `FINISHER` | Batter | +10 to skill in death overs (16-20) | Rare (10 weight) |
| `PARTNERSHIP_BREAKER` | Bowler | +10 to attack when partnership >= 40 runs | Uncommon (15 weight) |
| `DEATH_SPECIALIST` | Bowler | +8 to attack + control in overs 16-20 | New. Uncommon. |
| `POWERPLAY_EXPERT` | Bowler | +8 to attack + swing in overs 1-6 | New. Uncommon. |
| `BIG_MATCH` | Batter | +6 to all batting stats in playoff/final | New. Ultra rare. |
| `SLOW_STARTER` | Batter | -8 for first 10 balls, +5 after 20 balls | New. Common negative. |

Trait assignment follows v1's tier-weighted system (elite players = more positive traits, fewer negatives).

---

## 12. POC Simulation Plan

### POC Structure

A **standalone Python script** (no FastAPI, no database, no SQLAlchemy). Defines all data structures inline. Generates players, simulates matches, collects statistics, validates against benchmarks.

**File:** `scripts/poc_match_engine_v2.py`

### What the POC Implements

1. All data classes (BatterDNA, BowlerDNA, PitchDNA, Delivery, etc.)
2. Player generation with DNA + weaknesses
3. Full matchup engine (execution check → bowler attack → batter skill → Gaussian roll → outcome)
4. Pitch modifiers, ball age, fatigue
5. Commentary generation (basic templates, ~50-100 for POC)
6. Match simulation (20 overs, both innings, winner determination)
7. Statistics collection and validation

### What the POC Does NOT Implement

- API endpoints
- Database models
- UI components
- Field templates (use flat probability adjustments)
- Full commentary template library

### Test Categories

#### Category 1: Aggregate Realism (100+ matches)

Run 100-200 matches between balanced teams. Validate:

| Metric | Real T20 Benchmark | Acceptable Range |
|--------|-------------------|-----------------|
| Average innings score | 155-175 | 140-190 |
| Score std deviation | 25-35 | 20-45 |
| Min score (across all matches) | 70+ | 50+ |
| Max score (across all matches) | 240- | 270- |
| Average wickets per innings | 6-7 | 5-8 |
| Dot ball percentage | 38-42% | 33-48% |
| Boundary percentage (runs from 4s/6s) | 55-65% | 45-70% |
| Extras per innings | 8-12 | 5-15 |
| Powerplay avg score (overs 1-6) | 45-55 | 38-65 |
| Middle overs run rate (7-15) | 7.0-8.5 | 6.0-9.5 |
| Death overs run rate (16-20) | 9.0-11.0 | 8.0-13.0 |
| 50+ individual scores per match | ~1.5 | 0.8-2.5 |
| 100+ individual scores per match | ~0.08 | 0.02-0.15 |

#### Category 2: Matchup Validation (Specific Pairings)

Create named test scenarios with known expected outcomes:

**Test 2.1: Elite Batter vs Average Bowler**
- Batter: all stats 80+
- Bowler: all stats 55-65
- Expected: Batter SR > 145, wicket rate < 3%

**Test 2.2: Average Batter vs Elite Bowler**
- Batter: all stats 55-65
- Bowler: all stats 80+
- Expected: Batter SR < 110, wicket rate > 7%

**Test 2.3: Weakness Exploitation — Bouncer Plan vs Weak Back Foot**
- Batter: vs_bounce = 30, everything else = 75
- Bowler: bounce = 80, using bouncer delivery
- Expected: Wicket rate at least 40% higher than bowling good length to same batter

**Test 2.4: Strength Attack — Bouncer Plan vs Strong Back Foot**
- Batter: vs_bounce = 90, everything else = 75
- Bowler: bounce = 80, using bouncer delivery
- Expected: Batter SR > 140, fewer wickets than good length

**Test 2.5: Tactical Bonus Impact**
- Same batter, same bowler
- Run A: captain picks delivery that targets weakness (bonus +12)
- Run B: captain picks delivery that targets strength (bonus -12)
- Expected: Run A wicket rate 30-50% higher than Run B

**Test 2.6: Spinner on Dust Bowl vs Spinner on Green Top**
- Same spinner (turn: 70)
- Dust bowl: effective_turn = 94.5
- Green top: effective_turn = 45.5
- Expected: Dust bowl economy 1.5-2.5 RPO lower, more wickets

**Test 2.7: Pacer on Green Top vs Pacer on Dust Bowl**
- Same pacer (swing: 75)
- Green top: effective_swing = 97.5
- Dust bowl: effective_swing = 48.75
- Expected: Green top economy significantly lower

**Test 2.8: Tail-ender Viability**
- Batter: all stats 25-35
- Bowler: average (60-70)
- Expected: SR 60-90, rarely survives 15+ balls, but not out every ball

#### Category 3: Tactical System Validation

**Test 3.1: Execution Check Matters**
- High control bowler (85) attempting yorker (difficulty 58)
- Low control bowler (50) attempting yorker (difficulty 58)
- Expected: High control executes ~85% of time, low control ~50%

**Test 3.2: Fatigue Visible**
- Same bowler bowling overs 1, 2, 3, 4
- Expected: Economy increases by ~1 RPO between over 1 and over 4

**Test 3.3: Ball Age Swing Effect**
- Same swing bowler using outswinger in overs 1-6 vs overs 13-20
- Expected: Early overs have significantly more edges and wickets

**Test 3.4: Pitch Deterioration**
- Same batting lineup vs same bowling lineup
- First innings vs second innings on high-deterioration pitch
- Expected: Second innings spin wickets increase by 30-50%

**Test 3.5: Batting Approach Differences**
- Same matchup, four approaches: survive / rotate / push / all_out
- Expected: Monotonically increasing SR and wicket rate from survive to all_out

#### Category 4: Edge Cases & Sanity Checks

**Test 4.1: No All-Out-in-5-Overs Epidemic**
- 100 matches: fewer than 5% of innings should be all out before over 10

**Test 4.2: No 300+ Scores**
- 100 matches: max score should be below 280

**Test 4.3: Balanced Win Distribution**
- Equal teams: win rate should be ~48-52% each side (slight batting first advantage on neutral pitch)

**Test 4.4: Toss Impact on Deteriorating Pitch**
- 100 matches on dust bowl: batting first should win 55-65%

**Test 4.5: Captain Advantage Measurable**
- Team A: always picks optimal delivery (targets weakness)
- Team B: always picks random delivery
- Expected: Team A wins 60-70% of matches (not 90% — skill still matters)

**Test 4.6: Variety of Dismissal Types**
- Across 100 matches: all dismissal types should appear
- Caught: 40-55%, Bowled: 15-25%, LBW: 10-20%, Caught Behind: 8-15%, Stumped: 3-8%

### POC Output Format

The POC script should output:

```
============================================================
MATCH ENGINE v2 POC — SIMULATION RESULTS
============================================================

CATEGORY 1: AGGREGATE REALISM (200 matches)
------------------------------------------------------------
[OK] Average innings score:     162.3  (target: 140-190)
[OK] Score std deviation:       28.7   (target: 20-45)
[OK] Min score:                 73     (target: 50+)
[OK] Max score:                 247    (target: 270-)
[OK] Avg wickets/innings:       6.4    (target: 5-8)
[OK] Dot ball %:                39.2%  (target: 33-48%)
[OK] Boundary run %:            58.1%  (target: 45-70%)
[OK] Powerplay avg:             48.2   (target: 38-65)
[OK] Death overs RR:            10.1   (target: 8.0-13.0)
[FAIL] 50+ scores/match:       0.6    (target: 0.8-2.5)  ← NEEDS CALIBRATION
...

CATEGORY 2: MATCHUP VALIDATION
------------------------------------------------------------
[OK] Test 2.1 Elite vs Average:        SR=152.3, Wicket%=2.1%
[OK] Test 2.3 Weakness exploitation:   41% more wickets than baseline
[FAIL] Test 2.5 Tactical bonus:        Only 18% difference ← BONUS TOO SMALL?
...

CATEGORY 3: TACTICAL SYSTEM
------------------------------------------------------------
[OK] Test 3.1 High control exec:       87% vs 48% for low control
[OK] Test 3.2 Fatigue visible:         +1.3 RPO between over 1 and 4
...

CATEGORY 4: EDGE CASES
------------------------------------------------------------
[OK] Test 4.1 Early all-outs:          2.5% of innings (target: <5%)
[OK] Test 4.5 Captain advantage:       63% win rate (target: 60-70%)
...

============================================================
SUMMARY: 28/32 tests passed. 4 need calibration.
============================================================
```

### Calibration Parameters

When tests fail, these are the knobs to turn:

| Parameter | What It Affects | Current Value | Turn Up If... | Turn Down If... |
|-----------|---------------|---------------|--------------|----------------|
| `sigma` (Gaussian) | Overall variance | 10-14 by phase | Scores too clustered | Scores too wild |
| `tactical_bonus_multiplier` | Captain impact | 0.3 | Captain choices don't matter enough | Captain choices dominate |
| Edge zone range | Catch/wicket balance | -20 to -13 | Too few wickets from edges | Too many catches |
| Clean beat threshold | Clean wicket rate | <= -21 | Too few clean wickets | Too many clean wickets |
| Boundary distance thresholds | 4s and 6s frequency | 65m/75m | Not enough boundaries | Too many boundaries |
| `power` scaling | Six vs four ratio | 0.35 | Not enough sixes | Too many sixes |
| Execution difficulty values | Bowler accuracy | Per delivery | Too many full tosses | Bowlers too accurate |
| Fatigue multipliers | Late-over economy | 0.85 at over 4 | Fatigue not noticeable | Bowlers collapse |
| Settled modifier | New batter vulnerability | -5 to +5 | Set batters too easy to get out | New batters too safe |

---

## Appendix A: Migration Notes (v1 → v2)

### Player Model Changes

**New fields (batter DNA):**
- `vs_pace`, `vs_bounce`, `vs_spin`, `vs_deception`, `off_side`, `leg_side`
- `power` exists, kept as-is

**New fields (bowler DNA — pacers):**
- `speed`, `swing`, `bounce_ability` (renamed from generic), `control`

**New fields (bowler DNA — spinners):**
- `turn`, `flight`, `variation` (exists), `control`

**Repurposed fields:**
- `batting` → derived from average of batter DNA stats (for OVR/display)
- `bowling` → derived from average of bowler DNA stats (for OVR/display)
- `pace_or_spin` → split into `speed` (pacers) or `turn` (spinners)
- `accuracy` → becomes `control`
- `technique` → absorbed into `vs_pace` + `vs_spin`

**Removed from engine use (kept for display/OVR):**
- `fielding` → not used in v2 match engine (field templates handle this)
- `fitness` → replaced by fatigue system
- `running` → not directly modeled (runs from distance calculation)
- `temperament` → absorbed into traits
- `consistency` → absorbed into Gaussian sigma (consistent players = tighter sigma, future enhancement)

### API Changes Required (After POC)

- `POST /match/{id}/ball` → now accepts `delivery_type` parameter
- `POST /match/{id}/select-bowler` → response includes bowler repertoire
- `GET /match/{id}/state` → includes batter DNA summary for current batters
- New: `GET /match/{id}/pitch` → returns pitch DNA
- New: field template selection endpoint

### Database Migration

Will require an Alembic migration to:
1. Add new DNA columns to `players` table
2. Populate existing players with generated DNA values (backfill script)
3. Add pitch columns to `matches` table

This migration happens **after** POC validation, not before.

---

## Appendix B: What This Document Does NOT Cover (Future Phases)

- Phase 2 UI components (bowling plan selector, batter approach selector, scout report display)
- Phase 3 field placement visualization
- DRS (Decision Review System)
- Weather effects
- Player injuries mid-match
- Multi-format support (ODI, Test)
- AI captain decision-making (for opponent team)
- Multiplayer / head-to-head
