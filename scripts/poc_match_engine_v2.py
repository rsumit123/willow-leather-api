#!/usr/bin/env python3
"""
Match Engine v2 POC — Standalone simulation script.
No dependencies on the existing codebase. Pure Python + stdlib.

Run: python scripts/poc_match_engine_v2.py [num_matches]
"""

import random
import math
import sys
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from statistics import mean, stdev, median
from collections import Counter


# ================================================================
# 1. DATA CLASSES
# ================================================================

@dataclass
class BatterDNA:
    vs_pace: int = 50
    vs_bounce: int = 50
    vs_spin: int = 50
    vs_deception: int = 50
    off_side: int = 50
    leg_side: int = 50
    power: int = 50
    weaknesses: List[str] = field(default_factory=list)

    def avg(self):
        return (self.vs_pace + self.vs_bounce + self.vs_spin + self.vs_deception
                + self.off_side + self.leg_side) / 6


@dataclass
class PacerDNA:
    speed: int = 135      # kph, 120-155
    swing: int = 50
    bounce: int = 50
    control: int = 60

    def avg(self):
        return (self.speed_factor() + self.swing + self.bounce + self.control) / 4

    def speed_factor(self):
        """Normalize speed to 0-100 scale for calculations."""
        return max(0, min(100, (self.speed - 115) * 2.5))


@dataclass
class SpinnerDNA:
    turn: int = 50
    flight: int = 50
    variation: int = 50
    control: int = 60

    def avg(self):
        return (self.turn + self.flight + self.variation + self.control) / 4


@dataclass
class PitchDNA:
    name: str = "balanced"
    pace_assist: int = 55
    spin_assist: int = 45
    bounce: int = 60
    carry: int = 65
    deterioration: int = 35


@dataclass
class Delivery:
    name: str
    bowler_weights: Dict[str, float]
    batter_weights: Dict[str, float]
    exec_difficulty: int
    dismissal_weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class Player:
    name: str
    role: str                                   # batsman / bowler / all_rounder / wicket_keeper
    batting_dna: BatterDNA = field(default_factory=BatterDNA)
    bowler_dna: Optional[object] = None         # PacerDNA or SpinnerDNA
    bowling_type: str = "none"                  # pace / medium / off_spin / leg_spin / left_arm_spin
    traits: List[str] = field(default_factory=list)
    tier: str = "good"


@dataclass
class BallResult:
    runs: int = 0
    is_wicket: bool = False
    is_boundary: bool = False
    is_six: bool = False
    is_wide: bool = False
    is_no_ball: bool = False
    dismissal_type: str = ""
    contact_quality: str = ""
    execution: str = "executed"
    delivery_name: str = ""


@dataclass
class BatterInningsRecord:
    player_name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    is_out: bool = False
    dismissal: str = ""


@dataclass
class BowlerSpellRecord:
    player_name: str
    overs: int = 0
    balls_in_current: int = 0
    runs: int = 0
    wickets: int = 0
    dots: int = 0


@dataclass
class InningsState:
    batting_team: List[Player] = field(default_factory=list)
    bowling_team: List[Player] = field(default_factory=list)
    pitch: PitchDNA = field(default_factory=PitchDNA)
    is_second_innings: bool = False
    target: Optional[int] = None

    total_runs: int = 0
    wickets: int = 0
    overs: int = 0
    balls: int = 0
    extras: int = 0
    partnership_runs: int = 0

    striker_idx: int = 0
    non_striker_idx: int = 1
    next_batter_idx: int = 2
    last_bowler_name: str = ""

    batter_records: Dict[str, BatterInningsRecord] = field(default_factory=dict)
    bowler_records: Dict[str, BowlerSpellRecord] = field(default_factory=dict)
    bowler_overs_count: Dict[str, int] = field(default_factory=dict)
    balls_faced: Dict[str, int] = field(default_factory=dict)

    all_results: List[BallResult] = field(default_factory=list)

    @property
    def run_rate(self):
        total_b = self.overs * 6 + self.balls
        return (self.total_runs / total_b) * 6 if total_b > 0 else 0.0

    @property
    def is_complete(self):
        if self.wickets >= 10:
            return True
        if self.overs >= 20:
            return True
        if self.target and self.total_runs >= self.target:
            return True
        return False


# ================================================================
# 2. DELIVERY DEFINITIONS
# ================================================================

PACER_DELIVERIES = {
    "good_length": Delivery(
        name="good_length",
        bowler_weights={"control": 0.4, "swing": 0.3, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.7, "off_side": 0.3},
        exec_difficulty=30,
        dismissal_weights={"bowled": 0.25, "lbw": 0.20, "caught": 0.35, "caught_behind": 0.20},
    ),
    "outswinger": Delivery(
        name="outswinger",
        bowler_weights={"swing": 0.6, "control": 0.4},
        batter_weights={"vs_pace": 0.6, "off_side": 0.4},
        exec_difficulty=42,
        dismissal_weights={"caught_behind": 0.40, "caught": 0.30, "bowled": 0.20, "lbw": 0.10},
    ),
    "inswinger": Delivery(
        name="inswinger",
        bowler_weights={"swing": 0.6, "control": 0.4},
        batter_weights={"vs_pace": 0.5, "leg_side": 0.5},
        exec_difficulty=45,
        dismissal_weights={"lbw": 0.40, "bowled": 0.40, "caught": 0.15, "caught_behind": 0.05},
    ),
    "bouncer": Delivery(
        name="bouncer",
        bowler_weights={"bounce": 0.5, "speed_factor": 0.5},
        batter_weights={"vs_bounce": 0.6, "leg_side": 0.4},
        exec_difficulty=38,
        dismissal_weights={"caught": 0.55, "top_edge": 0.25, "bowled": 0.10, "hit_wicket": 0.10},
    ),
    "yorker": Delivery(
        name="yorker",
        bowler_weights={"control": 0.7, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.3, "power": 0.3, "leg_side": 0.4},
        exec_difficulty=58,
        dismissal_weights={"bowled": 0.50, "lbw": 0.35, "caught": 0.15},
    ),
    "slower_ball": Delivery(
        name="slower_ball",
        bowler_weights={"control": 0.5, "speed_factor": 0.5},
        batter_weights={"vs_deception": 0.7, "power": 0.3},
        exec_difficulty=48,
        dismissal_weights={"caught": 0.55, "bowled": 0.25, "lbw": 0.20},
    ),
    "wide_yorker": Delivery(
        name="wide_yorker",
        bowler_weights={"control": 0.7, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.3, "off_side": 0.7},
        exec_difficulty=55,
        dismissal_weights={"bowled": 0.40, "caught_behind": 0.35, "caught": 0.25},
    ),
}

SPINNER_DELIVERIES = {
    "stock_ball": Delivery(
        name="stock_ball",
        bowler_weights={"turn": 0.5, "control": 0.5},
        batter_weights={"vs_spin": 0.7, "off_side": 0.3},
        exec_difficulty=28,
        dismissal_weights={"bowled": 0.25, "stumped": 0.25, "caught": 0.25, "lbw": 0.15, "caught_behind": 0.10},
    ),
    "flighted": Delivery(
        name="flighted",
        bowler_weights={"flight": 0.6, "turn": 0.4},
        batter_weights={"vs_spin": 0.4, "vs_deception": 0.3, "power": 0.3},
        exec_difficulty=40,
        dismissal_weights={"stumped": 0.35, "caught": 0.35, "bowled": 0.15, "lbw": 0.15},
    ),
    "arm_ball": Delivery(
        name="arm_ball",
        bowler_weights={"variation": 0.7, "control": 0.3},
        batter_weights={"vs_deception": 0.8, "vs_spin": 0.2},
        exec_difficulty=52,
        dismissal_weights={"bowled": 0.40, "lbw": 0.30, "stumped": 0.15, "caught": 0.15},
    ),
    "flat_quick": Delivery(
        name="flat_quick",
        bowler_weights={"control": 0.7, "turn": 0.3},
        batter_weights={"power": 0.5, "vs_spin": 0.5},
        exec_difficulty=32,
        dismissal_weights={"caught": 0.40, "bowled": 0.30, "lbw": 0.20, "stumped": 0.10},
    ),
    "wide_of_off": Delivery(
        name="wide_of_off",
        bowler_weights={"control": 0.6, "turn": 0.4},
        batter_weights={"off_side": 0.6, "vs_spin": 0.4},
        exec_difficulty=38,
        dismissal_weights={"caught": 0.35, "stumped": 0.30, "caught_behind": 0.25, "bowled": 0.10},
    ),
}


# ================================================================
# 3. PITCH PRESETS
# ================================================================

PITCHES = {
    "green_seamer": PitchDNA("green_seamer", pace_assist=80, spin_assist=15, bounce=70, carry=85, deterioration=25),
    "dust_bowl":    PitchDNA("dust_bowl",    pace_assist=20, spin_assist=85, bounce=35, carry=45, deterioration=80),
    "flat_deck":    PitchDNA("flat_deck",    pace_assist=40, spin_assist=35, bounce=55, carry=60, deterioration=20),
    "bouncy_track": PitchDNA("bouncy_track", pace_assist=75, spin_assist=20, bounce=90, carry=85, deterioration=20),
    "slow_turner":  PitchDNA("slow_turner",  pace_assist=30, spin_assist=60, bounce=40, carry=50, deterioration=55),
    "balanced":     PitchDNA("balanced",     pace_assist=55, spin_assist=45, bounce=60, carry=65, deterioration=35),
}


# ================================================================
# 4. HELPER FUNCTIONS
# ================================================================

def clamp(val, lo=0, hi=100):
    return max(lo, min(hi, val))


def gen_attr(base, variance=12, minimum=5):
    """Generate attribute with variance, clamped 5-100."""
    return clamp(base + random.randint(-variance, variance), minimum, 100)


def speed_to_factor(speed_kph):
    """Normalize speed kph to 0-100 effectiveness scale."""
    return clamp((speed_kph - 115) * 2.5)


# --- STAT COMPRESSION ---
# Raw stats (0-100) produce too much spread when elite meets average.
# Compression narrows the effective range so skill matters but doesn't dominate.
# Maps: 0 → 28, 50 → 50.5, 85 → 66.25, 100 → 73
COMPRESS_BASE = 28
COMPRESS_SCALE = 0.45

def compress(rating: float) -> float:
    """Compress a raw 0-100 rating to a narrower effective range."""
    return COMPRESS_BASE + rating * COMPRESS_SCALE


def get_pitch_assist(pitch: PitchDNA, stat_name: str) -> int:
    """Map a bowler stat name to the relevant pitch assist value."""
    if stat_name in ("speed_factor", "swing"):
        return pitch.pace_assist
    if stat_name == "bounce":
        return (pitch.pace_assist + pitch.bounce) // 2
    if stat_name in ("turn", "flight"):
        return pitch.spin_assist
    if stat_name == "variation":
        return pitch.spin_assist * 7 // 10   # Variations less pitch-dependent
    return 50   # control, power, etc. — neutral


def ball_age_modifier(overs_bowled: int, stat_name: str) -> float:
    """Ball age affects swing and spin effectiveness."""
    if stat_name == "swing":
        if overs_bowled <= 6:
            return 1.0
        if overs_bowled <= 12:
            return 0.65
        return 0.40
    if stat_name in ("turn", "flight"):
        if overs_bowled <= 6:
            return 0.85
        if overs_bowled <= 12:
            return 1.0
        return 1.15
    return 1.0


def get_bowler_stat(bowler_dna, stat_name: str) -> float:
    """Get a bowler stat, handling speed_factor specially."""
    if stat_name == "speed_factor":
        if isinstance(bowler_dna, PacerDNA):
            return bowler_dna.speed_factor()
        return 30   # spinners have low "speed"
    return getattr(bowler_dna, stat_name, 50)


FATIGUE_MULTIPLIERS = {0: 1.0, 1: 1.0, 2: 0.97, 3: 0.92, 4: 0.85}


def get_fatigue(bowler_overs: int) -> float:
    return FATIGUE_MULTIPLIERS.get(bowler_overs, 0.85)


def get_sigma(overs: int) -> float:
    """Phase-based sigma for Gaussian roll."""
    if overs < 6:
        return 12.0    # Powerplay: moderate variance
    if overs < 16:
        return 11.0    # Middle overs: skill dominates
    return 14.0         # Death overs: high variance boom/bust


def get_settled_modifier(balls_faced: int) -> float:
    if balls_faced <= 5:
        return -3.0    # New batter vulnerable but not helpless
    if balls_faced <= 15:
        return 0.0
    if balls_faced <= 40:
        return 2.0
    return -1.0        # Slight complacency after long stint


def get_deterioration_mod(pitch: PitchDNA, is_second_innings: bool) -> float:
    """Returns multiplier for spin_assist in second innings."""
    if not is_second_innings:
        return 1.0
    return 1.0 + pitch.deterioration / 150


# ================================================================
# 5. PLAYER GENERATION
# ================================================================

def apply_weaknesses(dna: BatterDNA, num_weaknesses: int = None):
    """Force 1-2 weak attributes on every batter."""
    if num_weaknesses is None:
        num_weaknesses = random.choices([1, 2], weights=[55, 45])[0]

    candidates = ["vs_pace", "vs_bounce", "vs_spin", "vs_deception", "off_side", "leg_side"]
    weak_stats = random.sample(candidates, num_weaknesses)

    avg_val = dna.avg()
    for stat in weak_stats:
        reduction = random.randint(15, 25)
        new_val = clamp(int(avg_val - reduction), 10, 100)
        setattr(dna, stat, new_val)

    dna.weaknesses = weak_stats


def generate_batsman(name: str, base: int, tier: str = "good") -> Player:
    dna = BatterDNA(
        vs_pace=gen_attr(base + 5, 10),
        vs_bounce=gen_attr(base, 12),
        vs_spin=gen_attr(base, 12),
        vs_deception=gen_attr(base - 5, 15),
        off_side=gen_attr(base, 12),
        leg_side=gen_attr(base, 12),
        power=gen_attr(base - 5, 15),
    )
    apply_weaknesses(dna)
    return Player(name=name, role="batsman", batting_dna=dna, tier=tier)


def generate_bowler(name: str, base: int, bowling_type: str, tier: str = "good") -> Player:
    # Weak batting DNA
    bat_dna = BatterDNA(
        vs_pace=gen_attr(28, 10), vs_bounce=gen_attr(25, 10),
        vs_spin=gen_attr(25, 10), vs_deception=gen_attr(22, 10),
        off_side=gen_attr(25, 10), leg_side=gen_attr(28, 10),
        power=gen_attr(25, 10),
    )

    if bowling_type in ("pace", "medium"):
        speed_base = {"pace": 142, "medium": 132}[bowling_type]
        bowl_dna = PacerDNA(
            speed=clamp(speed_base + random.randint(-6, 6), 120, 155),
            swing=gen_attr(base, 15),
            bounce=gen_attr(base, 15),
            control=gen_attr(base + 5, 10),
        )
    else:
        bowl_dna = SpinnerDNA(
            turn=gen_attr(base + 5, 12),
            flight=gen_attr(base, 15),
            variation=gen_attr(base, 15),
            control=gen_attr(base + 5, 10),
        )

    return Player(name=name, role="bowler", batting_dna=bat_dna,
                  bowler_dna=bowl_dna, bowling_type=bowling_type, tier=tier)


def generate_allrounder(name: str, base: int, bowling_type: str, tier: str = "good") -> Player:
    dna = BatterDNA(
        vs_pace=gen_attr(base, 12), vs_bounce=gen_attr(base - 3, 12),
        vs_spin=gen_attr(base - 3, 12), vs_deception=gen_attr(base - 5, 12),
        off_side=gen_attr(base - 2, 12), leg_side=gen_attr(base - 2, 12),
        power=gen_attr(base - 5, 15),
    )
    apply_weaknesses(dna, num_weaknesses=1)

    if bowling_type in ("pace", "medium"):
        speed_base = {"pace": 138, "medium": 130}[bowling_type]
        bowl_dna = PacerDNA(
            speed=clamp(speed_base + random.randint(-5, 5), 120, 150),
            swing=gen_attr(base - 5, 12),
            bounce=gen_attr(base - 5, 12),
            control=gen_attr(base, 10),
        )
    else:
        bowl_dna = SpinnerDNA(
            turn=gen_attr(base, 12),
            flight=gen_attr(base - 5, 12),
            variation=gen_attr(base - 5, 12),
            control=gen_attr(base, 10),
        )

    return Player(name=name, role="all_rounder", batting_dna=dna,
                  bowler_dna=bowl_dna, bowling_type=bowling_type, tier=tier)


def generate_wk(name: str, base: int, tier: str = "good") -> Player:
    dna = BatterDNA(
        vs_pace=gen_attr(base, 12), vs_bounce=gen_attr(base - 3, 12),
        vs_spin=gen_attr(base + 2, 12), vs_deception=gen_attr(base - 2, 12),
        off_side=gen_attr(base, 12), leg_side=gen_attr(base + 3, 12),
        power=gen_attr(base - 5, 15),
    )
    apply_weaknesses(dna, num_weaknesses=1)
    return Player(name=name, role="wicket_keeper", batting_dna=dna, tier=tier)


def generate_team(tier: str = "good", name_prefix: str = "A") -> List[Player]:
    """Generate a realistic T20 team (4 bat + 1 WK + 2 AR + 4 bowlers)."""
    base = {"elite": 82, "star": 75, "good": 67, "solid": 60}[tier]
    return [
        generate_batsman(f"{name_prefix}-Opener1", base + 5, tier),
        generate_batsman(f"{name_prefix}-Opener2", base + 3, tier),
        generate_batsman(f"{name_prefix}-No3", base + 4, tier),
        generate_wk(f"{name_prefix}-WK4", base - 2, tier),
        generate_batsman(f"{name_prefix}-Bat5", base, tier),
        generate_allrounder(f"{name_prefix}-AR6", base - 3, "medium", tier),
        generate_allrounder(f"{name_prefix}-AR7", base - 5, "off_spin", tier),
        generate_bowler(f"{name_prefix}-Pace8", base + 2, "pace", tier),
        generate_bowler(f"{name_prefix}-Pace9", base, "pace", tier),
        generate_bowler(f"{name_prefix}-Spin10", base - 2, "leg_spin", tier),
        generate_bowler(f"{name_prefix}-Spin11", base + 1, "off_spin", tier),
    ]


# ================================================================
# 6. DELIVERY REPERTOIRE
# ================================================================

def get_repertoire(player: Player) -> List[Delivery]:
    """Get available deliveries for a bowler based on their DNA."""
    dna = player.bowler_dna
    if dna is None:
        return []

    if isinstance(dna, PacerDNA):
        deliveries = [PACER_DELIVERIES["good_length"]]
        if dna.swing >= 40:
            deliveries.append(PACER_DELIVERIES["outswinger"])
            deliveries.append(PACER_DELIVERIES["inswinger"])
        if dna.bounce >= 40:
            deliveries.append(PACER_DELIVERIES["bouncer"])
        deliveries.append(PACER_DELIVERIES["yorker"])
        deliveries.append(PACER_DELIVERIES["slower_ball"])
        if dna.control >= 55:
            deliveries.append(PACER_DELIVERIES["wide_yorker"])
        return deliveries

    if isinstance(dna, SpinnerDNA):
        deliveries = [SPINNER_DELIVERIES["stock_ball"]]
        if dna.flight >= 40:
            deliveries.append(SPINNER_DELIVERIES["flighted"])
        if dna.variation >= 45:
            deliveries.append(SPINNER_DELIVERIES["arm_ball"])
        deliveries.append(SPINNER_DELIVERIES["flat_quick"])
        if dna.control >= 50:
            deliveries.append(SPINNER_DELIVERIES["wide_of_off"])
        return deliveries

    return []


def choose_random_delivery(repertoire: List[Delivery]) -> Delivery:
    return random.choice(repertoire)


def choose_optimal_delivery(repertoire: List[Delivery], batter: Player) -> Delivery:
    """Captain picks smartly 60% of the time, random 40%.
    When smart, picks from top 3 with weighted random."""
    if random.random() < 0.45:
        return random.choice(repertoire)

    scored = []
    for d in repertoire:
        primary_stat = max(d.batter_weights, key=d.batter_weights.get)
        batter_val = getattr(batter.batting_dna, primary_stat, 50)
        advantage = 50 - batter_val
        scored.append((d, advantage))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_n = scored[:3]
    deliveries = [s[0] for s in top_n]
    weights = [3, 2, 1][:len(deliveries)]
    return random.choices(deliveries, weights=weights)[0]


# ================================================================
# 7. MATCH ENGINE CORE
# ================================================================

def execution_check(bowler: Player, delivery: Delivery, pitch: PitchDNA,
                    fatigue: float, overs: int) -> str:
    """Check if bowler lands the intended delivery."""
    control = bowler.bowler_dna.control * fatigue
    roll = random.gauss(control, 8)

    target = delivery.exec_difficulty
    # Phase modifier: new ball makes swing easier, old ball makes yorkers easier
    if overs < 6:
        if delivery.name in ("outswinger", "inswinger"):
            target -= 5
        elif delivery.name == "yorker":
            target += 5
    elif overs >= 16:
        if delivery.name in ("yorker", "wide_yorker", "slower_ball"):
            target -= 4
        elif delivery.name == "bouncer":
            target += 3

    if roll >= target:
        return "executed"
    miss = target - roll
    if miss > 15:
        return "bad_miss"
    return "slight_miss"


def bowler_attack_rating(bowler: Player, delivery: Delivery, pitch: PitchDNA,
                         overs: int, fatigue: float, is_second: bool) -> float:
    """Calculate how dangerous this delivery is."""
    rating = 0.0
    dna = bowler.bowler_dna

    for stat_name, weight in delivery.bowler_weights.items():
        base_stat = get_bowler_stat(dna, stat_name)

        pa = get_pitch_assist(pitch, stat_name)
        # Second innings deterioration boosts spin
        if is_second and stat_name in ("turn", "flight"):
            pa = min(100, pa * get_deterioration_mod(pitch, True))

        effective = base_stat * (0.5 + pa * 0.01)
        effective *= ball_age_modifier(overs, stat_name)
        effective *= fatigue
        effective = min(120, effective)   # Allow deteriorated pitches to push beyond normal max

        rating += effective * weight

    return rating


def batter_skill_rating(batter: Player, delivery: Delivery) -> float:
    """Calculate batter's skill against this specific delivery."""
    rating = 0.0
    for stat_name, weight in delivery.batter_weights.items():
        stat = getattr(batter.batting_dna, stat_name, 50)
        rating += stat * weight
    return rating


def tactical_bonus(batter: Player, delivery: Delivery) -> float:
    """How well does this delivery exploit the batter's weakness?
    Range: -7.5 to +7.5. Positive = exploiting weakness."""
    primary = max(delivery.batter_weights, key=delivery.batter_weights.get)
    primary_val = getattr(batter.batting_dna, primary, 50)
    raw = (50 - primary_val) * 0.10
    return max(-3.0, min(3.0, raw))


def calculate_margin(attack: float, skill: float, tac_bonus: float,
                     approach: str, sigma: float) -> float:
    """Gaussian roll to determine margin.
    Stats are compressed before this call so gaps are narrower.
    Approach modifies sigma (variance) with small mean shifts.
    Higher sigma = more extreme outcomes on BOTH sides."""
    approach_mods = {
        "survive":  (0.70, +3),     # Very tight variance, safe buffer
        "rotate":   (0.90, +1.5),   # Slightly safe, standard play
        "push":     (1.08, 0),      # More variance, neutral mean
        "all_out":  (1.25, 0),      # High variance, neutral mean
    }
    sigma_mult, base_shift = approach_mods.get(approach, (0.90, +1))
    adjusted_sigma = sigma * sigma_mult

    batter_performance = random.gauss(skill + base_shift, adjusted_sigma)
    difficulty = attack + tac_bonus

    return batter_performance - difficulty


def resolve_contact(margin: float) -> str:
    """Map margin to contact quality.
    Thresholds calibrated for compressed stat ranges (~28-73 effective).
    With sigma 10-14, these produce realistic T20 outcomes."""
    if margin >= 25:
        return "perfect"
    if margin >= 15:
        return "good"
    if margin >= 5:
        return "decent"
    if margin >= -5:
        return "defended"
    if margin >= -12:
        return "beaten"
    if margin >= -18:
        return "edge"
    return "clean_beat"


def resolve_runs(contact: str, power: int, margin: float,
                 pitch: PitchDNA, approach: str = "rotate") -> Tuple[int, bool, bool]:
    """
    Determine runs from contact quality.
    Approach affects run conversion: aggressive modes look for boundaries
    and run harder; defensive modes block and rotate.
    Returns (runs, is_boundary, is_six).
    """
    # Approach-specific adjustments
    boundary_mod = {"survive": -0.18, "rotate": 0, "push": +0.10, "all_out": +0.22}
    six_mod = {"survive": -0.10, "rotate": 0, "push": +0.05, "all_out": +0.15}
    bmod = boundary_mod.get(approach, 0)
    smod = six_mod.get(approach, 0)

    if contact == "perfect":
        six_chance = clamp(power / 160 + smod, 0.05, 0.75)
        if random.random() < six_chance:
            return 6, True, True
        return 4, True, False

    if contact == "good":
        boundary_chance = clamp(0.55 + power / 400 + bmod, 0.20, 0.90)
        if random.random() < boundary_chance:
            six_chance = clamp(power / 250 + smod, 0.02, 0.50)
            if random.random() < six_chance:
                return 6, True, True
            return 4, True, False
        if approach in ("push", "all_out"):
            return random.choice([2, 2, 3, 3]), False, False
        return random.choice([2, 2, 3]), False, False

    if contact == "decent":
        boundary_chance = clamp(0.08 + power / 800 + max(0, bmod * 0.5), 0.02, 0.25)
        if random.random() < boundary_chance:
            return 4, True, False
        if approach in ("push", "all_out"):
            return random.choice([1, 1, 2, 2, 2, 3]), False, False
        elif approach == "survive":
            return random.choice([0, 1, 1, 1, 1]), False, False
        return random.choice([1, 1, 1, 2, 2]), False, False

    if contact == "defended":
        if approach in ("push", "all_out"):
            return random.choice([0, 0, 1, 1, 1, 1]), False, False
        elif approach == "survive":
            return random.choice([0, 0, 0, 0, 1]), False, False
        return random.choice([0, 0, 0, 1, 1, 1]), False, False

    # beaten, edge, clean_beat handled elsewhere
    return 0, False, False


def resolve_edge(pitch: PitchDNA, catch_modifier: float = 0.0) -> Tuple[bool, str, int]:
    """Resolve edge: returns (is_wicket, dismissal_type, runs)."""
    carry = pitch.carry / 100
    catch_chance = 0.25 * carry + catch_modifier
    catch_chance = max(0.05, min(0.50, catch_chance))

    if random.random() < catch_chance:
        dismissal = random.choices(
            ["caught_behind", "caught"],
            weights=[0.55, 0.45]
        )[0]
        return True, dismissal, 0
    # Survived
    return False, "", random.choice([0, 0, 0, 1])


def resolve_clean_beat(margin: float, delivery: Delivery) -> Tuple[bool, str]:
    """Resolve clean beat: returns (is_wicket, dismissal_type)."""
    margin_abs = abs(margin)
    wicket_chance = min(0.95, 0.55 + (margin_abs - 18) * 0.025)

    if random.random() < wicket_chance:
        types = list(delivery.dismissal_weights.keys())
        weights = list(delivery.dismissal_weights.values())
        dismissal = random.choices(types, weights=weights)[0]
        return True, dismissal
    return False, ""


def safety_net(innings: InningsState) -> float:
    """Safety net for extreme scores. Activates earlier and stronger."""
    total_b = innings.overs * 6 + innings.balls
    if total_b < 6:
        return 0
    rr = innings.run_rate
    # Collapse protection: stronger boost when wickets falling fast
    if innings.wickets >= 5 and total_b < 36:
        return 15
    if rr < 4.0 and innings.wickets < 8:
        return 12
    if rr > 13:
        return -10
    return 0


def simulate_ball(bowler: Player, batter: Player, delivery: Delivery,
                  innings: InningsState, approach: str = "rotate",
                  catch_mod: float = 0.0) -> BallResult:
    """Full pipeline: execution → matchup → compression → Gaussian roll → outcome."""
    overs = innings.overs
    fatigue = get_fatigue(innings.bowler_overs_count.get(bowler.name, 0))
    sigma = get_sigma(overs)

    result = BallResult(delivery_name=delivery.name)

    # Step 0: Unplayable delivery (jaffa) — increases with balls faced
    # Models: perfect yorkers, unreadable googlies, freak run-outs, etc.
    # Base 0.5%, rises after 20 balls faced — specifically limits long innings
    bf = innings.balls_faced.get(batter.name, 0)
    jaffa_rate = 0.005 + max(0, bf - 20) * 0.0028
    if random.random() < jaffa_rate:
        result.is_wicket = True
        result.contact_quality = "clean_beat"
        types = list(delivery.dismissal_weights.keys())
        weights = list(delivery.dismissal_weights.values())
        result.dismissal_type = random.choices(types, weights=weights)[0]
        return result

    # Step 1: Execution check
    exec_result = execution_check(bowler, delivery, innings.pitch, fatigue, overs)
    result.execution = exec_result

    if exec_result == "bad_miss":
        batter_bonus = random.uniform(12, 18)
    elif exec_result == "slight_miss":
        batter_bonus = random.uniform(4, 10)
    else:
        batter_bonus = 0

    # Step 2: Bowler attack (raw 0-100)
    raw_attack = bowler_attack_rating(bowler, delivery, innings.pitch, overs,
                                      fatigue, innings.is_second_innings)

    # Step 3: Batter skill (raw 0-100)
    raw_skill = batter_skill_rating(batter, delivery) + batter_bonus

    # Tail-ender floor: only for genuinely weak batters (avg DNA < 40)
    # This protects tail-enders while allowing weakness exploitation for good batters
    if batter.batting_dna.avg() < 40:
        raw_skill = max(raw_skill, 63)

    # Settled modifier (applied before compression)
    bf = innings.balls_faced.get(batter.name, 0)
    raw_skill += get_settled_modifier(bf)

    # Safety net
    raw_skill += safety_net(innings)

    # Step 4: COMPRESS both ratings to narrow the effective range
    compressed_skill = compress(raw_skill)
    compressed_attack = compress(raw_attack)

    # Step 5: Tactical bonus (stays on compressed scale, max ±7.5)
    tac = tactical_bonus(batter, delivery)

    # Step 6: Gaussian margin
    margin = calculate_margin(compressed_attack, compressed_skill, tac, approach, sigma)

    # Step 7: Resolve
    contact = resolve_contact(margin)
    result.contact_quality = contact

    if contact in ("perfect", "good", "decent", "defended"):
        runs, is_boundary, is_six = resolve_runs(contact, batter.batting_dna.power,
                                                  margin, innings.pitch, approach)
        result.runs = runs
        result.is_boundary = is_boundary
        result.is_six = is_six
    elif contact == "beaten":
        result.runs = 0
    elif contact == "edge":
        is_w, dism, runs = resolve_edge(innings.pitch, catch_mod)
        result.is_wicket = is_w
        result.dismissal_type = dism
        result.runs = runs
    elif contact == "clean_beat":
        is_w, dism = resolve_clean_beat(margin, delivery)
        result.is_wicket = is_w
        result.dismissal_type = dism
        result.runs = 0

    return result


# ================================================================
# 8. MATCH SIMULATION
# ================================================================

def select_bowler(innings: InningsState) -> Player:
    """Auto-select bowler (weighted by skill, respects limits)."""
    bowlers = [p for p in innings.bowling_team if p.bowler_dna is not None]
    available = []
    for b in bowlers:
        ov = innings.bowler_overs_count.get(b.name, 0)
        if ov >= 4:
            continue
        if b.name == innings.last_bowler_name:
            continue
        available.append(b)

    if not available:
        available = [b for b in bowlers if b.name != innings.last_bowler_name]
    if not available:
        available = bowlers

    weights = [b.bowler_dna.avg() for b in available]
    return random.choices(available, weights=weights)[0]


def get_approach_for_situation(innings: InningsState) -> str:
    """Simple AI for batting approach based on match situation."""
    overs = innings.overs
    wickets = innings.wickets

    if innings.target:
        balls_left = (20 * 6) - (overs * 6 + innings.balls)
        if balls_left <= 0:
            return "all_out"
        rrr = ((innings.target - innings.total_runs) / balls_left) * 6
        if rrr > 14:
            return "all_out"
        if rrr > 10:
            return "push"
        if rrr < 5:
            return "rotate"

    if wickets >= 7:
        return "survive"
    if wickets >= 5 and overs < 12:
        return "rotate"
    if overs >= 16:
        return "push"
    if overs >= 18:
        return "all_out"
    return "rotate"


def simulate_innings(batting_team: List[Player], bowling_team: List[Player],
                     pitch: PitchDNA, target: int = None,
                     is_second: bool = False,
                     delivery_strategy: str = "random") -> InningsState:
    """Simulate a full T20 innings."""
    innings = InningsState(
        batting_team=batting_team,
        bowling_team=bowling_team,
        pitch=pitch,
        target=target,
        is_second_innings=is_second,
    )

    # Initialize opener records
    for i in range(2):
        p = batting_team[i]
        innings.batter_records[p.name] = BatterInningsRecord(player_name=p.name)
        innings.balls_faced[p.name] = 0

    while not innings.is_complete:
        # Select bowler for this over
        bowler = select_bowler(innings)
        innings.last_bowler_name = bowler.name
        repertoire = get_repertoire(bowler)

        if bowler.name not in innings.bowler_records:
            innings.bowler_records[bowler.name] = BowlerSpellRecord(player_name=bowler.name)

        spell = innings.bowler_records[bowler.name]
        balls_this_over = 0
        wickets_this_over = 0

        while balls_this_over < 6 and not innings.is_complete:
            striker = batting_team[innings.striker_idx]

            # Check extras (wider range for realistic extras count)
            extra_roll = random.random()
            fatigue = get_fatigue(innings.bowler_overs_count.get(bowler.name, 0))
            eff_ctrl = bowler.bowler_dna.control * fatigue
            # Higher base wide rate: control 85 → ~2.5%, control 50 → ~4.5%
            wide_chance = max(0.015, 0.06 - eff_ctrl * 0.0004)

            if extra_roll < wide_chance:
                innings.total_runs += 1
                innings.extras += 1
                spell.runs += 1
                innings.all_results.append(BallResult(runs=1, is_wide=True))
                continue

            if extra_roll < wide_chance + 0.008:  # 0.8% no-ball chance
                nb_runs = random.choices([0, 1, 2, 4, 6], weights=[30, 30, 10, 20, 10])[0]
                innings.total_runs += nb_runs + 1
                innings.extras += 1
                spell.runs += nb_runs + 1
                innings.all_results.append(BallResult(runs=nb_runs + 1, is_no_ball=True,
                                                      is_boundary=(nb_runs >= 4),
                                                      is_six=(nb_runs == 6)))
                continue

            # Choose delivery
            if delivery_strategy == "optimal":
                delivery = choose_optimal_delivery(repertoire, striker)
            else:
                delivery = choose_random_delivery(repertoire)

            # Determine batting approach
            approach = get_approach_for_situation(innings)

            # Simulate ball
            result = simulate_ball(bowler, striker, delivery, innings, approach)

            # Cap: max 3 wickets per over
            if result.is_wicket and wickets_this_over >= 3:
                result.is_wicket = False
                result.dismissal_type = ""
                result.runs = 0

            # Legal delivery
            balls_this_over += 1
            innings.balls += 1

            # Update batter record
            brec = innings.batter_records[striker.name]
            brec.balls += 1
            brec.runs += result.runs
            if result.is_boundary and not result.is_six:
                brec.fours += 1
            if result.is_six:
                brec.sixes += 1

            innings.balls_faced[striker.name] = innings.balls_faced.get(striker.name, 0) + 1

            # Update bowler record
            spell.runs += result.runs
            if result.runs == 0 and not result.is_wicket:
                spell.dots += 1

            # Update innings totals
            innings.total_runs += result.runs
            innings.partnership_runs += result.runs
            innings.all_results.append(result)

            # Handle wicket
            if result.is_wicket:
                wickets_this_over += 1
                innings.wickets += 1
                brec.is_out = True
                brec.dismissal = result.dismissal_type
                spell.wickets += 1
                innings.partnership_runs = 0

                # Bring in next batter
                if innings.next_batter_idx < len(batting_team):
                    innings.striker_idx = innings.next_batter_idx
                    next_p = batting_team[innings.striker_idx]
                    innings.batter_records[next_p.name] = BatterInningsRecord(player_name=next_p.name)
                    innings.balls_faced[next_p.name] = 0
                    innings.next_batter_idx += 1

            # Rotate strike on odd runs
            elif result.runs % 2 == 1:
                innings.striker_idx, innings.non_striker_idx = innings.non_striker_idx, innings.striker_idx

            # End of over bookkeeping
            if innings.balls >= 6:
                innings.overs += 1
                innings.balls = 0
                spell.overs += 1
                spell.balls_in_current = 0
                innings.bowler_overs_count[bowler.name] = innings.bowler_overs_count.get(bowler.name, 0) + 1
                # Rotate strike at end of over
                innings.striker_idx, innings.non_striker_idx = innings.non_striker_idx, innings.striker_idx
                break

    return innings


def simulate_match(team1: List[Player], team2: List[Player],
                   pitch: PitchDNA = None,
                   delivery_strategy_1: str = "random",
                   delivery_strategy_2: str = "random") -> dict:
    """Simulate a full T20 match. Team1 bats first."""
    if pitch is None:
        pitch = PITCHES["balanced"]

    inn1 = simulate_innings(team1, team2, pitch,
                            delivery_strategy=delivery_strategy_2)
    target = inn1.total_runs + 1
    inn2 = simulate_innings(team2, team1, pitch,
                            target=target, is_second=True,
                            delivery_strategy=delivery_strategy_1)

    if inn2.total_runs >= target:
        winner = "team2"
        margin_str = f"{10 - inn2.wickets} wickets"
    elif inn2.total_runs < target - 1:
        winner = "team1"
        margin_str = f"{(target - 1) - inn2.total_runs} runs"
    else:
        winner = "tie"
        margin_str = "tied"

    return {
        "inn1": inn1, "inn2": inn2,
        "winner": winner, "margin": margin_str,
        "score1": inn1.total_runs, "wkts1": inn1.wickets,
        "score2": inn2.total_runs, "wkts2": inn2.wickets,
    }


# ================================================================
# 9. STATISTICS HELPERS
# ================================================================

def innings_stats(inn: InningsState) -> dict:
    """Extract key stats from an innings."""
    total_legal = sum(1 for r in inn.all_results if not r.is_wide and not r.is_no_ball)
    dots = sum(1 for r in inn.all_results if r.runs == 0 and not r.is_wicket
               and not r.is_wide and not r.is_no_ball)
    boundaries = sum(1 for r in inn.all_results if r.is_boundary)
    sixes = sum(1 for r in inn.all_results if r.is_six)
    fours = boundaries - sixes

    boundary_runs = sum(r.runs for r in inn.all_results if r.is_boundary)

    dismissals = [r.dismissal_type for r in inn.all_results if r.is_wicket]

    contacts = Counter(r.contact_quality for r in inn.all_results
                       if not r.is_wide and not r.is_no_ball)

    # Phase scoring
    phase_runs = {"powerplay": 0, "middle": 0, "death": 0}
    phase_balls = {"powerplay": 0, "middle": 0, "death": 0}
    ball_idx = 0
    over_count = 0
    balls_in_over = 0
    for r in inn.all_results:
        if r.is_wide or r.is_no_ball:
            if over_count < 6:
                phase_runs["powerplay"] += r.runs
            elif over_count < 16:
                phase_runs["middle"] += r.runs
            else:
                phase_runs["death"] += r.runs
            continue

        if over_count < 6:
            phase = "powerplay"
        elif over_count < 16:
            phase = "middle"
        else:
            phase = "death"

        phase_runs[phase] += r.runs
        phase_balls[phase] += 1
        balls_in_over += 1
        if balls_in_over >= 6:
            over_count += 1
            balls_in_over = 0

    # Individual scores
    individual_scores = [br.runs for br in inn.batter_records.values()]
    fifties = sum(1 for s in individual_scores if 50 <= s < 100)
    hundreds = sum(1 for s in individual_scores if s >= 100)

    return {
        "runs": inn.total_runs,
        "wickets": inn.wickets,
        "overs": inn.overs + inn.balls / 6,
        "legal_balls": total_legal,
        "dots": dots,
        "dot_pct": (dots / total_legal * 100) if total_legal > 0 else 0,
        "boundaries": boundaries,
        "fours": fours,
        "sixes": sixes,
        "boundary_runs": boundary_runs,
        "boundary_run_pct": (boundary_runs / inn.total_runs * 100) if inn.total_runs > 0 else 0,
        "extras": inn.extras,
        "dismissals": Counter(dismissals),
        "contacts": contacts,
        "phase_runs": phase_runs,
        "phase_balls": phase_balls,
        "fifties": fifties,
        "hundreds": hundreds,
        "individual_scores": individual_scores,
    }


# ================================================================
# 10. TEST CATEGORIES
# ================================================================

def run_category_1(num_matches: int = 200) -> dict:
    """Category 1: Aggregate Realism."""
    print(f"\nCATEGORY 1: AGGREGATE REALISM ({num_matches} matches)")
    print("-" * 60)

    all_innings_stats = []
    all_match_results = []

    for i in range(num_matches):
        t1 = generate_team("good", f"T1_{i}")
        t2 = generate_team("good", f"T2_{i}")
        pitch = random.choice(list(PITCHES.values()))
        result = simulate_match(t1, t2, pitch)
        all_match_results.append(result)

        for inn_key in ("inn1", "inn2"):
            stats = innings_stats(result[inn_key])
            all_innings_stats.append(stats)

    # Aggregate
    scores = [s["runs"] for s in all_innings_stats]
    wickets = [s["wickets"] for s in all_innings_stats]
    dot_pcts = [s["dot_pct"] for s in all_innings_stats]
    boundary_run_pcts = [s["boundary_run_pct"] for s in all_innings_stats]
    extras_list = [s["extras"] for s in all_innings_stats]
    boundaries_list = [s["boundaries"] for s in all_innings_stats]
    sixes_list = [s["sixes"] for s in all_innings_stats]
    fours_list = [s["fours"] for s in all_innings_stats]

    pp_scores = [s["phase_runs"]["powerplay"] for s in all_innings_stats]
    mid_rr = []
    death_rr = []
    for s in all_innings_stats:
        mb = s["phase_balls"]["middle"]
        if mb > 0:
            mid_rr.append(s["phase_runs"]["middle"] / mb * 6)
        db = s["phase_balls"]["death"]
        if db > 0:
            death_rr.append(s["phase_runs"]["death"] / db * 6)

    fifties_per_match = [(all_innings_stats[i * 2]["fifties"] + all_innings_stats[i * 2 + 1]["fifties"])
                         for i in range(num_matches)]
    hundreds_per_match = [(all_innings_stats[i * 2]["hundreds"] + all_innings_stats[i * 2 + 1]["hundreds"])
                          for i in range(num_matches)]

    # All dismissal types
    all_dismissals = Counter()
    for s in all_innings_stats:
        all_dismissals.update(s["dismissals"])
    total_dismissals = sum(all_dismissals.values())

    # Contact distribution
    all_contacts = Counter()
    for s in all_innings_stats:
        all_contacts.update(s["contacts"])
    total_contacts = sum(all_contacts.values())

    results = {}

    def check(name, val, lo, hi, fmt=".1f"):
        passed = lo <= val <= hi
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {name:40s} {val:{fmt}}  (target: {lo}-{hi})")
        results[name] = passed
        return passed

    print()
    check("Average innings score", mean(scores), 130, 195)
    check("Score std deviation", stdev(scores), 18, 50)
    check("Min score", min(scores), 40, 999, "d")
    check("Max score", max(scores), 0, 280, "d")
    check("Average wickets/innings", mean(wickets), 4.5, 8.5)
    check("Dot ball %", mean(dot_pcts), 30, 50)
    check("Boundary run %", mean(boundary_run_pcts), 40, 75)
    check("Avg boundaries/innings", mean(boundaries_list), 10, 28)
    check("Avg fours/innings", mean(fours_list), 7, 22)
    check("Avg sixes/innings", mean(sixes_list), 2, 10)
    check("Avg extras/innings", mean(extras_list), 3, 18)
    check("Powerplay avg score", mean(pp_scores), 30, 70)
    if mid_rr:
        check("Middle overs RR", mean(mid_rr), 5.5, 10.0)
    if death_rr:
        check("Death overs RR", mean(death_rr), 7.0, 14.0)
    check("50+ scores per match", mean(fifties_per_match), 0.5, 3.0)
    check("100+ scores per match", mean(hundreds_per_match), 0.0, 0.25)

    # Dismissal distribution
    print(f"\n  Dismissal distribution ({total_dismissals} total):")
    for dtype in sorted(all_dismissals.keys()):
        pct = all_dismissals[dtype] / total_dismissals * 100
        print(f"    {dtype:20s} {pct:5.1f}%")

    # Contact distribution
    print(f"\n  Contact quality distribution ({total_contacts} balls):")
    for ctype in ["perfect", "good", "decent", "defended", "beaten", "edge", "clean_beat"]:
        ct = all_contacts.get(ctype, 0)
        pct = ct / total_contacts * 100 if total_contacts > 0 else 0
        print(f"    {ctype:15s} {pct:5.1f}%")

    return results


def run_category_2(num_balls: int = 1000) -> dict:
    """Category 2: Matchup Validation — specific player pairings."""
    print(f"\nCATEGORY 2: MATCHUP VALIDATION ({num_balls} balls per test)")
    print("-" * 60)

    results = {}
    pitch = PITCHES["balanced"]

    def run_balls(batter, bowler, delivery, approach="rotate", n=None):
        n = n or num_balls
        runs_total = 0
        wickets = 0
        boundaries = 0
        dummy_innings = InningsState(pitch=pitch)
        dummy_innings.balls_faced[batter.name] = 15   # Assume settled

        for _ in range(n):
            r = simulate_ball(bowler, batter, delivery, dummy_innings, approach)
            runs_total += r.runs
            if r.is_wicket:
                wickets += 1
            if r.is_boundary:
                boundaries += 1

        sr = (runs_total / n) * 100
        wkt_pct = (wickets / n) * 100
        bnd_pct = (boundaries / n) * 100
        return {"sr": sr, "wkt_pct": wkt_pct, "bnd_pct": bnd_pct,
                "runs": runs_total, "wickets": wickets}

    # Test 2.1: Elite batter vs Average bowler
    elite_bat = Player("EliteBat", "batsman", BatterDNA(85, 82, 83, 78, 84, 80, 82))
    avg_bowler = Player("AvgPacer", "bowler",
                         bowler_dna=PacerDNA(speed=135, swing=55, bounce=50, control=62),
                         bowling_type="pace")
    d21 = PACER_DELIVERIES["good_length"]
    r21 = run_balls(elite_bat, avg_bowler, d21)

    passed = r21["sr"] > 140 and r21["wkt_pct"] < 4
    results["2.1 Elite bat vs Avg bowler"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.1 Elite bat vs Avg bowler:   SR={r21['sr']:.1f}  Wkt%={r21['wkt_pct']:.1f}%  "
          f"(want: SR>140, Wkt<4%)")

    # Test 2.2: Average batter vs Elite bowler
    avg_bat = Player("AvgBat", "batsman", BatterDNA(58, 55, 56, 52, 55, 57, 50))
    elite_bowler = Player("ElitePacer", "bowler",
                           bowler_dna=PacerDNA(speed=148, swing=82, bounce=78, control=88),
                           bowling_type="pace")
    r22 = run_balls(avg_bat, elite_bowler, d21)

    passed = r22["sr"] < 115 and r22["wkt_pct"] > 5
    results["2.2 Avg bat vs Elite bowler"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.2 Avg bat vs Elite bowler:   SR={r22['sr']:.1f}  Wkt%={r22['wkt_pct']:.1f}%  "
          f"(want: SR<115, Wkt>5%)")

    # Test 2.3: Weakness exploitation — bouncer vs weak vs_bounce
    weak_bounce_bat = Player("WeakBounce", "batsman", BatterDNA(75, 30, 75, 70, 72, 74, 65))
    strong_pacer = Player("BounceKing", "bowler",
                          bowler_dna=PacerDNA(speed=142, swing=70, bounce=82, control=72),
                          bowling_type="pace")

    bouncer = PACER_DELIVERIES["bouncer"]
    r23_exploit = run_balls(weak_bounce_bat, strong_pacer, bouncer)
    r23_baseline = run_balls(weak_bounce_bat, strong_pacer, d21)

    wkt_ratio = r23_exploit["wkt_pct"] / max(0.1, r23_baseline["wkt_pct"])
    passed = wkt_ratio >= 1.3
    results["2.3 Weakness exploitation"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.3 Weakness exploit (bouncer vs low vs_bounce):  "
          f"Exploit Wkt={r23_exploit['wkt_pct']:.1f}% vs Baseline={r23_baseline['wkt_pct']:.1f}%  "
          f"Ratio={wkt_ratio:.2f}x (want: >=1.3x)")

    # Test 2.4: Strength attack — bouncer vs strong vs_bounce
    strong_bounce_bat = Player("StrongBounce", "batsman", BatterDNA(75, 90, 75, 70, 72, 74, 70))
    # Use the same strong_pacer from 2.3 (bounce=82, from generated bowler)
    r24 = run_balls(strong_bounce_bat, strong_pacer, bouncer)

    passed = r24["sr"] > 130
    results["2.4 Strength attack"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.4 Strength attack (bouncer vs high vs_bounce):  "
          f"SR={r24['sr']:.1f}  Wkt%={r24['wkt_pct']:.1f}% (want: SR>130)")

    # Test 2.5: Tactical bonus measurable
    # Same batter with a clear weakness, test optimal vs random delivery
    weakness_bat = Player("HasWeakness", "batsman", BatterDNA(72, 72, 72, 30, 70, 70, 60))
    test_spinner = Player("TrickSpin", "bowler",
                           bowler_dna=SpinnerDNA(turn=75, flight=65, variation=78, control=72),
                           bowling_type="leg_spin")

    arm_ball = SPINNER_DELIVERIES["arm_ball"]   # Tests vs_deception (weakness=30)
    stock = SPINNER_DELIVERIES["stock_ball"]     # Tests vs_spin (72, no weakness)

    r25_exploit = run_balls(weakness_bat, test_spinner, arm_ball)
    r25_neutral = run_balls(weakness_bat, test_spinner, stock)

    wkt_diff = r25_exploit["wkt_pct"] - r25_neutral["wkt_pct"]
    passed = wkt_diff > 1.5
    results["2.5 Tactical bonus measurable"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.5 Tactical bonus (exploit weakness vs neutral):  "
          f"Exploit={r25_exploit['wkt_pct']:.1f}% vs Neutral={r25_neutral['wkt_pct']:.1f}%  "
          f"Diff={wkt_diff:.1f}pp (want: >1.5pp)")

    # Test 2.6: Spinner on dust bowl vs green top
    test_spin2 = Player("SpinTest", "bowler",
                         bowler_dna=SpinnerDNA(turn=72, flight=65, variation=60, control=70),
                         bowling_type="off_spin")
    test_bat2 = Player("AvgBat2", "batsman", BatterDNA(65, 60, 58, 55, 62, 63, 55))
    stock2 = SPINNER_DELIVERIES["stock_ball"]

    dummy_dust = InningsState(pitch=PITCHES["dust_bowl"])
    dummy_dust.balls_faced[test_bat2.name] = 15
    dummy_green = InningsState(pitch=PITCHES["green_seamer"])
    dummy_green.balls_faced[test_bat2.name] = 15

    dust_runs, dust_wkts = 0, 0
    green_runs, green_wkts = 0, 0
    for _ in range(num_balls):
        r = simulate_ball(test_spin2, test_bat2, stock2, dummy_dust)
        dust_runs += r.runs
        dust_wkts += 1 if r.is_wicket else 0
    for _ in range(num_balls):
        r = simulate_ball(test_spin2, test_bat2, stock2, dummy_green)
        green_runs += r.runs
        green_wkts += 1 if r.is_wicket else 0

    dust_econ = dust_runs / num_balls * 6
    green_econ = green_runs / num_balls * 6

    passed = dust_econ < green_econ and dust_wkts > green_wkts
    results["2.6 Spinner pitch impact"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.6 Spinner pitch impact:  Dust Bowl econ={dust_econ:.1f} wkts={dust_wkts}  "
          f"vs Green Top econ={green_econ:.1f} wkts={green_wkts}")

    # Test 2.7: Pacer on green top vs dust bowl
    test_pacer = Player("PaceTest", "bowler",
                         bowler_dna=PacerDNA(speed=140, swing=68, bounce=65, control=70),
                         bowling_type="pace")
    gl = PACER_DELIVERIES["good_length"]

    dummy_green2 = InningsState(pitch=PITCHES["green_seamer"])
    dummy_green2.balls_faced[test_bat2.name] = 15
    dummy_dust2 = InningsState(pitch=PITCHES["dust_bowl"])
    dummy_dust2.balls_faced[test_bat2.name] = 15

    green_r, green_w = 0, 0
    dust_r, dust_w = 0, 0
    for _ in range(num_balls):
        r = simulate_ball(test_pacer, test_bat2, gl, dummy_green2)
        green_r += r.runs
        green_w += 1 if r.is_wicket else 0
    for _ in range(num_balls):
        r = simulate_ball(test_pacer, test_bat2, gl, dummy_dust2)
        dust_r += r.runs
        dust_w += 1 if r.is_wicket else 0

    g_econ = green_r / num_balls * 6
    d_econ = dust_r / num_balls * 6

    passed = g_econ < d_econ
    results["2.7 Pacer pitch impact"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.7 Pacer pitch impact:  Green Top econ={g_econ:.1f} wkts={green_w}  "
          f"vs Dust Bowl econ={d_econ:.1f} wkts={dust_w}")

    # Test 2.8: Tail-ender viability
    tail = Player("Tailender", "bowler", BatterDNA(28, 25, 22, 20, 25, 28, 20))
    avg_bowl2 = Player("AvgBowl2", "bowler",
                        bowler_dna=PacerDNA(speed=137, swing=65, bounce=58, control=68),
                        bowling_type="pace")
    r28 = run_balls(tail, avg_bowl2, d21)

    passed = 50 < r28["sr"] < 100 and r28["wkt_pct"] > 5
    results["2.8 Tail-ender viability"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 2.8 Tail-ender viability:  SR={r28['sr']:.1f}  Wkt%={r28['wkt_pct']:.1f}%  "
          f"(want: 50<SR<100, Wkt>5%)")

    return results


def run_category_3(num_balls: int = 800) -> dict:
    """Category 3: Tactical System Validation."""
    print(f"\nCATEGORY 3: TACTICAL SYSTEM VALIDATION ({num_balls} balls per test)")
    print("-" * 60)

    results = {}
    pitch = PITCHES["balanced"]

    # Test 3.1: Execution check — high vs low control
    hi_ctrl = Player("HiCtrl", "bowler",
                     bowler_dna=PacerDNA(speed=140, swing=65, bounce=60, control=88),
                     bowling_type="pace")
    lo_ctrl = Player("LoCtrl", "bowler",
                     bowler_dna=PacerDNA(speed=140, swing=65, bounce=60, control=50),
                     bowling_type="pace")

    yorker = PACER_DELIVERIES["yorker"]
    hi_exec, lo_exec = 0, 0
    for _ in range(num_balls):
        r = execution_check(hi_ctrl, yorker, pitch, 1.0, 10)
        if r == "executed":
            hi_exec += 1
        r = execution_check(lo_ctrl, yorker, pitch, 1.0, 10)
        if r == "executed":
            lo_exec += 1

    hi_pct = hi_exec / num_balls * 100
    lo_pct = lo_exec / num_balls * 100

    passed = hi_pct > lo_pct + 15
    results["3.1 Execution check"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 3.1 Execution check (yorker):  High ctrl={hi_pct:.1f}%  Low ctrl={lo_pct:.1f}%  "
          f"(want: >15pp diff)")

    # Test 3.2: Fatigue visible
    test_bowler = Player("FatigueTest", "bowler",
                          bowler_dna=PacerDNA(speed=140, swing=65, bounce=60, control=72),
                          bowling_type="pace")
    test_batter = Player("FatBat", "batsman", BatterDNA(65, 62, 63, 60, 64, 63, 58))
    gl = PACER_DELIVERIES["good_length"]

    fresh_runs, tired_runs = 0, 0
    for _ in range(num_balls):
        dummy = InningsState(pitch=pitch)
        dummy.balls_faced[test_batter.name] = 15
        dummy.bowler_overs_count[test_bowler.name] = 0   # Fresh
        r = simulate_ball(test_bowler, test_batter, gl, dummy)
        fresh_runs += r.runs

    for _ in range(num_balls):
        dummy = InningsState(pitch=pitch)
        dummy.balls_faced[test_batter.name] = 15
        dummy.bowler_overs_count[test_bowler.name] = 4   # Tired
        r = simulate_ball(test_bowler, test_batter, gl, dummy)
        tired_runs += r.runs

    fresh_econ = fresh_runs / num_balls * 6
    tired_econ = tired_runs / num_balls * 6

    passed = tired_econ > fresh_econ + 0.3
    results["3.2 Fatigue visible"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 3.2 Fatigue visible:  Fresh econ={fresh_econ:.2f}  Tired econ={tired_econ:.2f}  "
          f"Diff={tired_econ - fresh_econ:.2f} (want: >0.3)")

    # Test 3.3: Ball age — swing more effective early
    swing_bowler = Player("SwingTest", "bowler",
                           bowler_dna=PacerDNA(speed=140, swing=80, bounce=60, control=68),
                           bowling_type="pace")
    outsw = PACER_DELIVERIES["outswinger"]
    test_bat3 = Player("SwingBat", "batsman", BatterDNA(65, 62, 63, 60, 64, 63, 58))

    early_wkts, late_wkts = 0, 0
    for _ in range(num_balls):
        dummy = InningsState(pitch=pitch)
        dummy.overs = 2   # Early (new ball)
        dummy.balls_faced[test_bat3.name] = 15
        r = simulate_ball(swing_bowler, test_bat3, outsw, dummy)
        early_wkts += 1 if r.is_wicket else 0

    for _ in range(num_balls):
        dummy = InningsState(pitch=pitch)
        dummy.overs = 17   # Late (old ball)
        dummy.balls_faced[test_bat3.name] = 15
        r = simulate_ball(swing_bowler, test_bat3, outsw, dummy)
        late_wkts += 1 if r.is_wicket else 0

    passed = early_wkts > late_wkts
    results["3.3 Ball age swing effect"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 3.3 Ball age (swing early vs late):  Early wkts={early_wkts}  Late wkts={late_wkts}  "
          f"(want: early > late)")

    # Test 3.4: Pitch deterioration — spin harder in 2nd innings
    spin_bowler = Player("DetSpin", "bowler",
                          bowler_dna=SpinnerDNA(turn=72, flight=65, variation=60, control=70),
                          bowling_type="off_spin")
    stock = SPINNER_DELIVERIES["stock_ball"]
    det_bat = Player("DetBat", "batsman", BatterDNA(65, 60, 55, 52, 62, 60, 55))
    dust = PITCHES["dust_bowl"]

    first_wkts, second_wkts = 0, 0
    for _ in range(num_balls):
        dummy = InningsState(pitch=dust, is_second_innings=False)
        dummy.balls_faced[det_bat.name] = 15
        r = simulate_ball(spin_bowler, det_bat, stock, dummy)
        first_wkts += 1 if r.is_wicket else 0

    for _ in range(num_balls):
        dummy = InningsState(pitch=dust, is_second_innings=True)
        dummy.balls_faced[det_bat.name] = 15
        r = simulate_ball(spin_bowler, det_bat, stock, dummy)
        second_wkts += 1 if r.is_wicket else 0

    passed = second_wkts > first_wkts
    results["3.4 Pitch deterioration"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 3.4 Pitch deterioration (dust bowl):  1st inn wkts={first_wkts}  "
          f"2nd inn wkts={second_wkts} (want: 2nd > 1st)")

    # Test 3.5: Batting approach differences
    app_bat = Player("AppBat", "batsman", BatterDNA(70, 68, 65, 63, 70, 68, 65))
    app_bowl = Player("AppBowl", "bowler",
                       bowler_dna=PacerDNA(speed=138, swing=62, bounce=58, control=70),
                       bowling_type="pace")
    app_d = PACER_DELIVERIES["good_length"]

    approaches = ["survive", "rotate", "push", "all_out"]
    app_results = {}

    for app in approaches:
        app_runs, app_wkts = 0, 0
        for _ in range(num_balls):
            dummy = InningsState(pitch=pitch)
            dummy.balls_faced[app_bat.name] = 15
            r = simulate_ball(app_bowl, app_bat, app_d, dummy, approach=app)
            app_runs += r.runs
            app_wkts += 1 if r.is_wicket else 0
        app_results[app] = {"sr": app_runs / num_balls * 100, "wkt_pct": app_wkts / num_balls * 100}

    sr_monotonic = (app_results["survive"]["sr"] <= app_results["rotate"]["sr"]
                    <= app_results["push"]["sr"] <= app_results["all_out"]["sr"])
    wkt_monotonic = (app_results["survive"]["wkt_pct"] <= app_results["rotate"]["wkt_pct"]
                     <= app_results["push"]["wkt_pct"] <= app_results["all_out"]["wkt_pct"])

    passed = sr_monotonic and wkt_monotonic
    results["3.5 Batting approach monotonic"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 3.5 Batting approach monotonic:")
    for app in approaches:
        ar = app_results[app]
        print(f"       {app:10s}  SR={ar['sr']:.1f}  Wkt%={ar['wkt_pct']:.1f}%")
    if sr_monotonic:
        print(f"       SR order: OK")
    else:
        print(f"       SR order: FAILED (not monotonically increasing)")
    if wkt_monotonic:
        print(f"       Wkt order: OK")
    else:
        print(f"       Wkt order: FAILED (not monotonically increasing)")

    return results


def run_category_4(num_matches: int = 100) -> dict:
    """Category 4: Edge Cases & Sanity Checks."""
    print(f"\nCATEGORY 4: EDGE CASES & SANITY ({num_matches} matches)")
    print("-" * 60)

    results = {}

    # Test 4.1: No all-out-in-5-overs epidemic
    early_allouts = 0
    total_innings = 0
    all_scores = []
    t1_wins = 0

    for i in range(num_matches):
        t1 = generate_team("good", f"E1_{i}")
        t2 = generate_team("good", f"E2_{i}")
        pitch = PITCHES["balanced"]
        result = simulate_match(t1, t2, pitch)

        for inn in (result["inn1"], result["inn2"]):
            total_innings += 1
            all_scores.append(inn.total_runs)
            if inn.wickets >= 10 and inn.overs <= 10:
                early_allouts += 1

        if result["winner"] == "team1":
            t1_wins += 1

    early_pct = early_allouts / total_innings * 100
    passed = early_pct < 5
    results["4.1 No early all-outs"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 4.1 No early all-outs:  {early_pct:.1f}% of innings all out by over 10  (want: <5%)")

    # Test 4.2: No 300+ scores
    max_score = max(all_scores)
    passed = max_score < 300
    results["4.2 No extreme scores"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 4.2 No extreme scores:  Max score = {max_score}  (want: <300)")

    # Test 4.3: Balanced win distribution (equal teams)
    t1_pct = t1_wins / num_matches * 100
    passed = 35 <= t1_pct <= 65
    results["4.3 Balanced wins"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 4.3 Balanced wins:  Team1 wins {t1_pct:.1f}%  (want: 35-65%)")

    # Test 4.4: Deteriorating pitch favors batting first
    dust_t1_wins = 0
    for i in range(num_matches):
        t1 = generate_team("good", f"D1_{i}")
        t2 = generate_team("good", f"D2_{i}")
        result = simulate_match(t1, t2, PITCHES["dust_bowl"])
        if result["winner"] == "team1":
            dust_t1_wins += 1

    dust_pct = dust_t1_wins / num_matches * 100
    passed = dust_pct > 50
    results["4.4 Dust bowl bats-first advantage"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 4.4 Dust bowl bats-first advantage:  Bat-first wins {dust_pct:.1f}%  (want: >50%)")

    # Test 4.5: Captain advantage — optimal vs random delivery
    opt_wins = 0
    for i in range(num_matches):
        t1 = generate_team("good", f"O1_{i}")
        t2 = generate_team("good", f"O2_{i}")
        pitch = PITCHES["balanced"]
        # t1 bowls with optimal strategy, t2 bowls random
        result = simulate_match(t1, t2, pitch,
                                delivery_strategy_1="optimal",
                                delivery_strategy_2="random")
        # t1 bats first. When bowling (2nd innings), t1 uses optimal.
        # When t2 bowls (1st innings), t2 uses random.
        # So t1 has optimal bowling in 2nd innings, t2 has random bowling in 1st innings.
        # Net: t1 gets attacked randomly, t1 attacks optimally.
        if result["winner"] == "team1":
            opt_wins += 1

    opt_pct = opt_wins / num_matches * 100
    passed = 55 <= opt_pct <= 80
    results["4.5 Captain advantage"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 4.5 Captain advantage (optimal bowling):  Wins={opt_pct:.1f}%  (want: 55-80%)")

    # Test 4.6: Variety of dismissal types
    all_dismissals = Counter()
    for i in range(num_matches):
        t1 = generate_team("good", f"V1_{i}")
        t2 = generate_team("good", f"V2_{i}")
        result = simulate_match(t1, t2, PITCHES["balanced"])
        for inn in (result["inn1"], result["inn2"]):
            for r in inn.all_results:
                if r.is_wicket and r.dismissal_type:
                    all_dismissals[r.dismissal_type] += 1

    total_d = sum(all_dismissals.values())
    caught_pct = (all_dismissals.get("caught", 0) + all_dismissals.get("caught_behind", 0) + all_dismissals.get("top_edge", 0)) / total_d * 100 if total_d > 0 else 0
    bowled_pct = all_dismissals.get("bowled", 0) / total_d * 100 if total_d > 0 else 0
    lbw_pct = all_dismissals.get("lbw", 0) / total_d * 100 if total_d > 0 else 0

    has_variety = len(all_dismissals) >= 4 and caught_pct > 30 and bowled_pct > 10 and lbw_pct > 5
    results["4.6 Dismissal variety"] = has_variety
    status = "[OK]" if has_variety else "[FAIL]"
    print(f"  {status} 4.6 Dismissal variety:  Types={len(all_dismissals)}  "
          f"Caught(all)={caught_pct:.1f}%  Bowled={bowled_pct:.1f}%  LBW={lbw_pct:.1f}%")
    print(f"       Full breakdown: {dict(all_dismissals)}")

    return results


# ================================================================
# 10b. EXTENDED BALL RUNNER (for granular matchup tests)
# ================================================================

def run_balls_extended(batter, bowler, delivery, pitch=None, approach="rotate",
                       n=3000, overs=10, settled_balls=15):
    """Run n balls and track extended stats: sixes, dismissal types, contacts."""
    if pitch is None:
        pitch = PITCHES["balanced"]
    runs_total = 0
    wickets = 0
    boundaries = 0
    sixes = 0
    fours = 0
    dismissal_types = Counter()
    contacts = Counter()

    dummy_innings = InningsState(pitch=pitch)
    dummy_innings.overs = overs
    dummy_innings.balls_faced[batter.name] = settled_balls

    for _ in range(n):
        r = simulate_ball(bowler, batter, delivery, dummy_innings, approach)
        runs_total += r.runs
        if r.is_wicket:
            wickets += 1
            if r.dismissal_type:
                dismissal_types[r.dismissal_type] += 1
        if r.is_boundary:
            boundaries += 1
        if r.is_six:
            sixes += 1
        if r.is_boundary and not r.is_six:
            fours += 1
        if r.contact_quality:
            contacts[r.contact_quality] += 1

    sr = (runs_total / n) * 100
    wkt_pct = (wickets / n) * 100
    bnd_pct = (boundaries / n) * 100
    return {
        "sr": sr, "wkt_pct": wkt_pct, "bnd_pct": bnd_pct,
        "runs": runs_total, "wickets": wickets,
        "boundaries": boundaries, "sixes": sixes, "fours": fours,
        "dismissal_types": dismissal_types, "contacts": contacts,
    }


# ================================================================
# 10c. CATEGORIES 5-11: GRANULAR MATCHUP VALIDATION
# ================================================================

def run_category_5(num_balls: int = 3000) -> dict:
    """Category 5: Weakness Exploitation Matrix — each batter weakness tested."""
    print(f"\nCATEGORY 5: WEAKNESS EXPLOITATION MATRIX ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    # Standard bowler for pace tests
    pace_bowler = Player("WknessPacer", "bowler",
                         bowler_dna=PacerDNA(speed=140, swing=70, bounce=70, control=72),
                         bowling_type="pace")
    # Standard bowler for spin tests
    spin_bowler = Player("WknessSpin", "bowler",
                         bowler_dna=SpinnerDNA(turn=72, flight=65, variation=72, control=70),
                         bowling_type="off_spin")

    # Base batter DNA: all stats at 70 except the one weakness
    base_stats = {"vs_pace": 70, "vs_bounce": 70, "vs_spin": 70,
                  "vs_deception": 70, "off_side": 70, "leg_side": 70, "power": 65}

    tests = [
        # (test_id, weakness_stat, weakness_val, exploit_delivery, baseline_delivery, bowler, min_diff_pp)
        ("5.1", "vs_pace", 25, "good_length", "bouncer", pace_bowler, 0.8),
        ("5.2", "vs_bounce", 25, "bouncer", "good_length", pace_bowler, 0.5),
        ("5.3", "vs_spin", 25, "stock_ball", "arm_ball", spin_bowler, 0.5),
        ("5.4", "vs_deception", 25, "arm_ball", "stock_ball", spin_bowler, 1.0),
        ("5.5", "off_side", 25, "wide_yorker", "inswinger", pace_bowler, 0.5),
        ("5.6", "leg_side", 25, "inswinger", "outswinger", pace_bowler, 0.5),
    ]

    for test_id, weak_stat, weak_val, exploit_name, baseline_name, bowler, min_diff in tests:
        # Create batter with one weakness
        stats = dict(base_stats)
        stats[weak_stat] = weak_val
        batter = Player(f"Weak{weak_stat}", "batsman",
                        BatterDNA(**stats))

        # Get deliveries
        if isinstance(bowler.bowler_dna, PacerDNA):
            exploit_d = PACER_DELIVERIES[exploit_name]
            baseline_d = PACER_DELIVERIES[baseline_name]
        else:
            exploit_d = SPINNER_DELIVERIES[exploit_name]
            baseline_d = SPINNER_DELIVERIES[baseline_name]

        r_exploit = run_balls_extended(batter, bowler, exploit_d, n=num_balls)
        r_baseline = run_balls_extended(batter, bowler, baseline_d, n=num_balls)

        diff = r_exploit["wkt_pct"] - r_baseline["wkt_pct"]
        passed = diff >= min_diff
        results[f"{test_id} Weakness {weak_stat}"] = passed
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {test_id} Low {weak_stat} ({weak_val}):  "
              f"Exploit({exploit_name}) Wkt%={r_exploit['wkt_pct']:.1f}%  "
              f"Baseline({baseline_name}) Wkt%={r_baseline['wkt_pct']:.1f}%  "
              f"Diff={diff:.1f}pp (want: ≥{min_diff}pp)")

    return results


def run_category_6(num_balls: int = 3000) -> dict:
    """Category 6: Batter Strength Domination — high vs moderate stats."""
    print(f"\nCATEGORY 6: BATTER STRENGTH DOMINATION ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    pace_bowler = Player("StrPacer", "bowler",
                         bowler_dna=PacerDNA(speed=142, swing=68, bounce=70, control=72),
                         bowling_type="pace")
    spin_bowler = Player("StrSpin", "bowler",
                         bowler_dna=SpinnerDNA(turn=72, flight=65, variation=68, control=70),
                         bowling_type="off_spin")

    base = {"vs_pace": 65, "vs_bounce": 65, "vs_spin": 65,
            "vs_deception": 65, "off_side": 65, "leg_side": 65, "power": 60}

    skill_tests = [
        # (test_id, stat, high_val, mod_val, delivery_name, bowler, min_sr_delta, delivery_set)
        ("6.1", "vs_pace", 90, 50, "good_length", pace_bowler, 15, "pace"),
        ("6.2", "vs_bounce", 90, 50, "bouncer", pace_bowler, 10, "pace"),
        ("6.3", "vs_spin", 90, 50, "stock_ball", spin_bowler, 10, "spin"),
        ("6.4", "vs_deception", 90, 50, "arm_ball", spin_bowler, 15, "spin"),
    ]

    for test_id, stat, high_val, mod_val, del_name, bowler, min_sr_delta, del_set in skill_tests:
        high_stats = dict(base)
        high_stats[stat] = high_val
        mod_stats = dict(base)
        mod_stats[stat] = mod_val

        high_bat = Player(f"High{stat}", "batsman", BatterDNA(**high_stats))
        mod_bat = Player(f"Mod{stat}", "batsman", BatterDNA(**mod_stats))

        delivery = PACER_DELIVERIES[del_name] if del_set == "pace" else SPINNER_DELIVERIES[del_name]

        r_high = run_balls_extended(high_bat, bowler, delivery, n=num_balls)
        r_mod = run_balls_extended(mod_bat, bowler, delivery, n=num_balls)

        sr_delta = r_high["sr"] - r_mod["sr"]
        wkt_lower = r_high["wkt_pct"] < r_mod["wkt_pct"]
        passed = sr_delta >= min_sr_delta and wkt_lower
        results[f"{test_id} Strength {stat}"] = passed
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {test_id} {stat} ({high_val} vs {mod_val}):  "
              f"High SR={r_high['sr']:.1f} Wkt%={r_high['wkt_pct']:.1f}%  "
              f"Mod SR={r_mod['sr']:.1f} Wkt%={r_mod['wkt_pct']:.1f}%  "
              f"SR delta={sr_delta:.1f} (want: ≥{min_sr_delta})")

    # Test 6.5: Power hitting — high power vs low power six counts
    high_pow_bat = Player("HighPow", "batsman",
                          BatterDNA(70, 70, 70, 70, 70, 70, 92))
    low_pow_bat = Player("LowPow", "batsman",
                         BatterDNA(70, 70, 70, 70, 70, 70, 30))

    delivery = PACER_DELIVERIES["good_length"]
    r_hipow = run_balls_extended(high_pow_bat, pace_bowler, delivery, n=num_balls)
    r_lopow = run_balls_extended(low_pow_bat, pace_bowler, delivery, n=num_balls)

    six_ratio = r_hipow["sixes"] / max(1, r_lopow["sixes"])
    passed = six_ratio >= 1.5
    results["6.5 Power hitting sixes"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 6.5 Power (92 vs 30):  "
          f"High sixes={r_hipow['sixes']}  Low sixes={r_lopow['sixes']}  "
          f"Ratio={six_ratio:.2f}x (want: ≥1.5x)")

    return results


def run_category_7(num_balls: int = 3000) -> dict:
    """Category 7: Equal Skill Matchups — balanced results for same-tier players."""
    print(f"\nCATEGORY 7: EQUAL SKILL MATCHUPS ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    matchups = [
        ("7.1", "Good bat vs Good pacer",
         Player("GoodBat1", "batsman", BatterDNA(68, 65, 66, 63, 67, 66, 60)),
         Player("GoodPacer1", "bowler",
                bowler_dna=PacerDNA(speed=140, swing=65, bounce=62, control=68),
                bowling_type="pace"),
         PACER_DELIVERIES["good_length"]),
        ("7.2", "Elite bat vs Elite pacer",
         Player("EliteBat2", "batsman", BatterDNA(88, 85, 84, 82, 86, 84, 80)),
         Player("ElitePacer2", "bowler",
                bowler_dna=PacerDNA(speed=148, swing=82, bounce=78, control=85),
                bowling_type="pace"),
         PACER_DELIVERIES["good_length"]),
        ("7.3", "Good bat vs Good spinner",
         Player("GoodBat3", "batsman", BatterDNA(68, 65, 66, 63, 67, 66, 60)),
         Player("GoodSpin3", "bowler",
                bowler_dna=SpinnerDNA(turn=68, flight=62, variation=65, control=68),
                bowling_type="off_spin"),
         SPINNER_DELIVERIES["stock_ball"]),
    ]

    for test_id, label, batter, bowler, delivery in matchups:
        r = run_balls_extended(batter, bowler, delivery, n=num_balls)
        # Isolated ball tests inherently favor batters (no progressive jaffa, always settled)
        # so SR is higher and Wkt% lower than match-level averages
        sr_ok = 120 <= r["sr"] <= 310
        wkt_ok = 0.2 <= r["wkt_pct"] <= 5.0
        passed = sr_ok and wkt_ok
        results[f"{test_id} {label}"] = passed
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {test_id} {label}:  SR={r['sr']:.1f}  Wkt%={r['wkt_pct']:.1f}%  "
              f"(want: SR 120-310, Wkt% 0.2-5.0%)")

    return results


def run_category_8(num_balls: int = 3000) -> dict:
    """Category 8: All Pitch Variations — each pitch favors its type."""
    print(f"\nCATEGORY 8: ALL PITCH VARIATIONS ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    test_batter = Player("PitchBat", "batsman", BatterDNA(68, 65, 64, 62, 66, 65, 60))
    test_pacer = Player("PitchPacer", "bowler",
                        bowler_dna=PacerDNA(speed=140, swing=68, bounce=68, control=70),
                        bowling_type="pace")
    test_spinner = Player("PitchSpin", "bowler",
                          bowler_dna=SpinnerDNA(turn=70, flight=65, variation=65, control=70),
                          bowling_type="off_spin")

    gl = PACER_DELIVERIES["good_length"]
    bouncer = PACER_DELIVERIES["bouncer"]
    stock = SPINNER_DELIVERIES["stock_ball"]

    # Run pacer and spinner on all pitches
    pitch_pacer_results = {}
    pitch_spinner_results = {}
    pitch_bouncer_results = {}
    pitch_batter_sr = {}

    for pname, pitch in PITCHES.items():
        r_pace = run_balls_extended(test_batter, test_pacer, gl, pitch=pitch, n=num_balls)
        r_spin = run_balls_extended(test_batter, test_spinner, stock, pitch=pitch, n=num_balls)
        r_bnc = run_balls_extended(test_batter, test_pacer, bouncer, pitch=pitch, n=num_balls)
        pitch_pacer_results[pname] = r_pace
        pitch_spinner_results[pname] = r_spin
        pitch_bouncer_results[pname] = r_bnc
        # Average batter SR across pace and spin
        pitch_batter_sr[pname] = (r_pace["sr"] + r_spin["sr"]) / 2

    # Test 8.1: Green seamer — pacer more effective than on flat deck
    green_pace_wkt = pitch_pacer_results["green_seamer"]["wkt_pct"]
    flat_pace_wkt = pitch_pacer_results["flat_deck"]["wkt_pct"]
    passed = green_pace_wkt > flat_pace_wkt
    results["8.1 Green seamer pace boost"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.1 Green seamer pace:  Wkt%={green_pace_wkt:.1f}% vs Flat={flat_pace_wkt:.1f}%  "
          f"(want: green > flat)")

    # Test 8.2: Dust bowl — spinner more effective than on flat deck
    dust_spin_wkt = pitch_spinner_results["dust_bowl"]["wkt_pct"]
    flat_spin_wkt = pitch_spinner_results["flat_deck"]["wkt_pct"]
    passed = dust_spin_wkt > flat_spin_wkt
    results["8.2 Dust bowl spin boost"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.2 Dust bowl spin:  Wkt%={dust_spin_wkt:.1f}% vs Flat={flat_spin_wkt:.1f}%  "
          f"(want: dust > flat)")

    # Test 8.3: Flat deck — highest or near-highest batter SR
    flat_sr = pitch_batter_sr["flat_deck"]
    max_sr = max(pitch_batter_sr.values())
    passed = flat_sr >= max_sr - 5
    results["8.3 Flat deck best for batting"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.3 Flat deck batting:  SR={flat_sr:.1f}  Max SR={max_sr:.1f}  "
          f"(want: within 5 of max)")
    for pname, sr in sorted(pitch_batter_sr.items(), key=lambda x: -x[1]):
        print(f"       {pname:16s}  avg SR={sr:.1f}")

    # Test 8.4: Bouncy track — bouncer more effective than on flat deck
    bouncy_bnc_wkt = pitch_bouncer_results["bouncy_track"]["wkt_pct"]
    flat_bnc_wkt = pitch_bouncer_results["flat_deck"]["wkt_pct"]
    passed = bouncy_bnc_wkt > flat_bnc_wkt
    results["8.4 Bouncy track bouncer boost"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.4 Bouncy bouncer:  Wkt%={bouncy_bnc_wkt:.1f}% vs Flat={flat_bnc_wkt:.1f}%  "
          f"(want: bouncy > flat)")

    # Test 8.5: Bouncy track — pacer more effective than spinner
    # Check either more wickets OR harder to score off (lower batter SR)
    bouncy_pace_wkt = pitch_pacer_results["bouncy_track"]["wkt_pct"]
    bouncy_spin_wkt = pitch_spinner_results["bouncy_track"]["wkt_pct"]
    bouncy_pace_sr = pitch_pacer_results["bouncy_track"]["sr"]
    bouncy_spin_sr = pitch_spinner_results["bouncy_track"]["sr"]
    passed = (bouncy_pace_wkt > bouncy_spin_wkt) or (bouncy_pace_sr < bouncy_spin_sr)
    results["8.5 Bouncy track pace > spin"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.5 Bouncy track:  Pacer Wkt%={bouncy_pace_wkt:.1f}% SR={bouncy_pace_sr:.1f}  "
          f"Spinner Wkt%={bouncy_spin_wkt:.1f}% SR={bouncy_spin_sr:.1f} "
          f"(want: pacer more effective)")

    # Test 8.6: Slow turner — spinner more effective than pacer
    slow_spin_wkt = pitch_spinner_results["slow_turner"]["wkt_pct"]
    slow_pace_wkt = pitch_pacer_results["slow_turner"]["wkt_pct"]
    passed = slow_spin_wkt > slow_pace_wkt
    results["8.6 Slow turner spin > pace"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 8.6 Slow turner:  Spinner Wkt%={slow_spin_wkt:.1f}%  "
          f"Pacer Wkt%={slow_pace_wkt:.1f}% (want: spinner > pacer)")

    return results


def run_category_9(num_balls: int = 3000) -> dict:
    """Category 9: Bowler Type Comparisons."""
    print(f"\nCATEGORY 9: BOWLER TYPE COMPARISONS ({num_balls} balls per test)")
    print("-" * 60)

    results = {}
    test_batter = Player("TypeBat", "batsman", BatterDNA(68, 65, 66, 63, 67, 66, 60))

    # Test 9.1: Express pace vs medium pace
    express = Player("Express", "bowler",
                     bowler_dna=PacerDNA(speed=148, swing=60, bounce=65, control=68),
                     bowling_type="pace")
    medium = Player("Medium", "bowler",
                    bowler_dna=PacerDNA(speed=130, swing=60, bounce=65, control=68),
                    bowling_type="medium")

    gl = PACER_DELIVERIES["good_length"]
    r_express = run_balls_extended(test_batter, express, gl, n=num_balls)
    r_medium = run_balls_extended(test_batter, medium, gl, n=num_balls)

    # Express should be more effective: lower SR or higher Wkt%
    express_better = (r_express["sr"] < r_medium["sr"]) or (r_express["wkt_pct"] > r_medium["wkt_pct"])
    results["9.1 Express > medium pace"] = express_better
    status = "[OK]" if express_better else "[FAIL]"
    print(f"  {status} 9.1 Express(148kph) vs Medium(130kph):  "
          f"Express SR={r_express['sr']:.1f} Wkt%={r_express['wkt_pct']:.1f}%  "
          f"Medium SR={r_medium['sr']:.1f} Wkt%={r_medium['wkt_pct']:.1f}%")

    # Test 9.2: High swing vs high bounce — different dismissal profiles
    swing_pacer = Player("SwingKing", "bowler",
                         bowler_dna=PacerDNA(speed=138, swing=88, bounce=45, control=70),
                         bowling_type="pace")
    bounce_pacer = Player("BounceKing", "bowler",
                          bowler_dna=PacerDNA(speed=142, swing=45, bounce=88, control=70),
                          bowling_type="pace")

    outsw = PACER_DELIVERIES["outswinger"]
    bnc = PACER_DELIVERIES["bouncer"]

    r_swing = run_balls_extended(test_batter, swing_pacer, outsw, n=num_balls)
    r_bounce = run_balls_extended(test_batter, bounce_pacer, bnc, n=num_balls)

    swing_total = sum(r_swing["dismissal_types"].values())
    bounce_total = sum(r_bounce["dismissal_types"].values())

    swing_cb_pct = (r_swing["dismissal_types"].get("caught_behind", 0) / max(1, swing_total)) * 100
    bounce_caught_pct = ((r_bounce["dismissal_types"].get("caught", 0) +
                          r_bounce["dismissal_types"].get("top_edge", 0)) / max(1, bounce_total)) * 100

    # Swing should have more caught_behind, bounce should have more caught/top_edge
    passed = swing_cb_pct > 20 and bounce_caught_pct > 40
    results["9.2 Swing vs bounce dismissals"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 9.2 Swing vs Bounce dismissal profiles:")
    print(f"       Swing caught_behind={swing_cb_pct:.1f}%  ({dict(r_swing['dismissal_types'])})")
    print(f"       Bounce caught+top_edge={bounce_caught_pct:.1f}%  ({dict(r_bounce['dismissal_types'])})")

    # Test 9.3: Off-spin vs leg-spin — both effective, possibly different characteristics
    off_spinner = Player("Offie", "bowler",
                         bowler_dna=SpinnerDNA(turn=70, flight=62, variation=60, control=72),
                         bowling_type="off_spin")
    leg_spinner = Player("Leggie", "bowler",
                         bowler_dna=SpinnerDNA(turn=70, flight=62, variation=70, control=65),
                         bowling_type="leg_spin")

    stock = SPINNER_DELIVERIES["stock_ball"]
    r_off = run_balls_extended(test_batter, off_spinner, stock, n=num_balls)
    r_leg = run_balls_extended(test_batter, leg_spinner, stock, n=num_balls)

    # Both should be reasonably effective in isolated ball tests
    both_effective = (r_off["wkt_pct"] > 0.5 and r_leg["wkt_pct"] > 0.5 and
                      r_off["sr"] < 250 and r_leg["sr"] < 250)
    results["9.3 Off-spin vs leg-spin"] = both_effective
    status = "[OK]" if both_effective else "[FAIL]"
    print(f"  {status} 9.3 Off-spin vs Leg-spin:  "
          f"Off SR={r_off['sr']:.1f} Wkt%={r_off['wkt_pct']:.1f}%  "
          f"Leg SR={r_leg['sr']:.1f} Wkt%={r_leg['wkt_pct']:.1f}%  "
          f"(want: both SR<250, Wkt%>0.5%)")

    return results


def run_category_10(num_balls: int = 3000) -> dict:
    """Category 10: Power Hitting mechanics."""
    print(f"\nCATEGORY 10: POWER HITTING ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    bowler = Player("PowBowl", "bowler",
                    bowler_dna=PacerDNA(speed=138, swing=62, bounce=58, control=68),
                    bowling_type="pace")
    gl = PACER_DELIVERIES["good_length"]

    high_pow = Player("HighPow", "batsman",
                      BatterDNA(70, 70, 70, 70, 70, 70, 92))
    low_pow = Player("LowPow", "batsman",
                     BatterDNA(70, 70, 70, 70, 70, 70, 30))

    r_hi = run_balls_extended(high_pow, bowler, gl, n=num_balls)
    r_lo = run_balls_extended(low_pow, bowler, gl, n=num_balls)

    # Test 10.1: Six count ratio
    six_ratio = r_hi["sixes"] / max(1, r_lo["sixes"])
    passed = six_ratio >= 1.5
    results["10.1 Power six count"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 10.1 Six count (pow 92 vs 30):  "
          f"High={r_hi['sixes']}  Low={r_lo['sixes']}  "
          f"Ratio={six_ratio:.2f}x (want: ≥1.5x)")

    # Test 10.2: Six share of boundaries
    hi_six_share = r_hi["sixes"] / max(1, r_hi["sixes"] + r_hi["fours"]) * 100
    lo_six_share = r_lo["sixes"] / max(1, r_lo["sixes"] + r_lo["fours"]) * 100
    passed = hi_six_share > lo_six_share
    results["10.2 Power six share"] = passed
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} 10.2 Six share of boundaries:  "
          f"High={hi_six_share:.1f}%  Low={lo_six_share:.1f}%  "
          f"(want: high > low)")

    return results


def run_category_11(num_balls: int = 5000) -> dict:
    """Category 11: Delivery Dismissal Patterns — characteristic dismissals."""
    print(f"\nCATEGORY 11: DELIVERY DISMISSAL PATTERNS ({num_balls} balls per test)")
    print("-" * 60)

    results = {}

    # Use a weaker batter to generate more clean_beat dismissals (which follow
    # delivery.dismissal_weights) vs edges (which are always caught/caught_behind)
    test_batter = Player("DisBat", "batsman", BatterDNA(50, 48, 48, 45, 50, 50, 42))

    pace_bowler = Player("DisPacer", "bowler",
                         bowler_dna=PacerDNA(speed=142, swing=72, bounce=72, control=72),
                         bowling_type="pace")
    spin_bowler = Player("DisSpin", "bowler",
                         bowler_dna=SpinnerDNA(turn=72, flight=70, variation=72, control=70),
                         bowling_type="off_spin")

    delivery_tests = [
        # (test_id, delivery_name, bowler, expected_types, min_pct, delivery_set)
        ("11.1", "bouncer", pace_bowler,
         ["caught", "top_edge"], 60, "pace"),
        ("11.2", "inswinger", pace_bowler,
         ["lbw", "bowled"], 42, "pace"),
        ("11.3", "outswinger", pace_bowler,
         ["caught_behind", "caught"], 50, "pace"),
        ("11.4", "yorker", pace_bowler,
         ["bowled", "lbw"], 55, "pace"),
        ("11.5", "flighted", spin_bowler,
         ["stumped", "caught"], 50, "spin"),
        ("11.6", "arm_ball", spin_bowler,
         ["bowled", "lbw"], 40, "spin"),
    ]

    for test_id, del_name, bowler, expected_types, min_pct, del_set in delivery_tests:
        delivery = PACER_DELIVERIES[del_name] if del_set == "pace" else SPINNER_DELIVERIES[del_name]
        r = run_balls_extended(test_batter, bowler, delivery, n=num_balls)

        total_wkts = sum(r["dismissal_types"].values())
        if total_wkts > 0:
            expected_count = sum(r["dismissal_types"].get(t, 0) for t in expected_types)
            actual_pct = expected_count / total_wkts * 100
        else:
            actual_pct = 0

        passed = actual_pct >= min_pct and total_wkts >= 30
        results[f"{test_id} {del_name} dismissals"] = passed
        status = "[OK]" if passed else "[FAIL]"
        types_str = "+".join(expected_types)
        print(f"  {status} {test_id} {del_name}:  {types_str}={actual_pct:.1f}%  "
              f"({total_wkts} wkts)  (want: ≥{min_pct}%)")
        print(f"       Breakdown: {dict(r['dismissal_types'])}")

    return results


# ================================================================
# 11. MAIN
# ================================================================

def main():
    num_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    print("=" * 60)
    print("MATCH ENGINE v2 POC — SIMULATION RESULTS")
    print("=" * 60)

    # Quick sanity: single match
    print("\n--- Quick Sanity: Single Match ---")
    t1 = generate_team("good", "Mumbai")
    t2 = generate_team("good", "Chennai")
    result = simulate_match(t1, t2, PITCHES["balanced"])
    print(f"  {result['score1']}/{result['wkts1']} vs {result['score2']}/{result['wkts2']}  "
          f"Winner: {result['winner']} by {result['margin']}")

    # Show a sample batter DNA
    print(f"\n  Sample batter DNA ({t1[0].name}):")
    dna = t1[0].batting_dna
    print(f"    vs_pace={dna.vs_pace} vs_bounce={dna.vs_bounce} vs_spin={dna.vs_spin} "
          f"vs_deception={dna.vs_deception}")
    print(f"    off_side={dna.off_side} leg_side={dna.leg_side} power={dna.power}")
    print(f"    weaknesses={dna.weaknesses}")

    # Show a sample bowler DNA
    bowler = t1[7]
    print(f"  Sample bowler DNA ({bowler.name}):")
    bd = bowler.bowler_dna
    if isinstance(bd, PacerDNA):
        print(f"    speed={bd.speed}kph swing={bd.swing} bounce={bd.bounce} control={bd.control}")
    else:
        print(f"    turn={bd.turn} flight={bd.flight} variation={bd.variation} control={bd.control}")
    print(f"    repertoire: {[d.name for d in get_repertoire(bowler)]}")

    # Run all categories
    r1 = run_category_1(num_matches)
    r2 = run_category_2(2000)
    r3 = run_category_3(1500)
    r4 = run_category_4(num_matches)
    r5 = run_category_5(3000)
    r6 = run_category_6(3000)
    r7 = run_category_7(3000)
    r8 = run_category_8(3000)
    r9 = run_category_9(3000)
    r10 = run_category_10(3000)
    r11 = run_category_11(5000)

    # Final summary
    all_results = {}
    all_results.update(r1)
    all_results.update(r2)
    all_results.update(r3)
    all_results.update(r4)
    all_results.update(r5)
    all_results.update(r6)
    all_results.update(r7)
    all_results.update(r8)
    all_results.update(r9)
    all_results.update(r10)
    all_results.update(r11)

    passed = sum(1 for v in all_results.values() if v)
    total = len(all_results)
    failed_tests = [k for k, v in all_results.items() if not v]

    print("\n" + "=" * 60)
    print(f"FINAL SUMMARY: {passed}/{total} tests passed")
    print("=" * 60)

    if failed_tests:
        print("\nFailed tests:")
        for t in failed_tests:
            print(f"  - {t}")
    else:
        print("\nAll tests passed!")

    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
