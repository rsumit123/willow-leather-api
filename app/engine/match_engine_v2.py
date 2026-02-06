"""
Match Engine v2 — DNA-based T20 cricket simulation.
Ported from POC (scripts/poc_match_engine_v2.py), wrapped in a class
compatible with the existing match API.
"""
from __future__ import annotations

import random
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Union, TYPE_CHECKING, Any

from app.engine.dna import (
    BatterDNA, PacerDNA, SpinnerDNA, PitchDNA, PITCHES, clamp,
)
from app.engine.deliveries import (
    Delivery, PACER_DELIVERIES, SPINNER_DELIVERIES,
)

if TYPE_CHECKING:
    from app.models.player import Player


# Role/type constants to avoid importing from player model at runtime
_BOWLER_ROLES = {"bowler", "all_rounder"}
_PACE_TYPES = {"pace", "medium"}
_SPIN_TYPES = {"off_spin", "leg_spin", "left_arm_spin"}


def _get_role_str(player) -> str:
    """Get role as string from Player (handles both enum and string)."""
    role = player.role
    return role.value if hasattr(role, 'value') else str(role)


# ================================================================
# DATACLASSES (compatible with existing API)
# ================================================================

@dataclass
class MatchContext:
    """Dynamic match context affecting all calculations"""
    pitch_type: str = "balanced"
    is_pressure_cooker: bool = False
    partnership_runs: int = 0


@dataclass
class BatterState:
    """Extended batter state with status effects"""
    player_id: int
    balls_faced: int = 0
    is_settled: bool = False
    is_on_fire: bool = False
    recent_outcomes: list = field(default_factory=list)


@dataclass
class BowlerState:
    """Extended bowler state"""
    player_id: int
    consecutive_overs: int = 0
    is_tired: bool = False
    has_confidence: bool = False


@dataclass
class BatterInnings:
    """Tracks a batter's innings"""
    player: Player
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    is_out: bool = False
    dismissal: str = ""
    bowler: Optional[Player] = None
    fielder: Optional[Player] = None

    @property
    def strike_rate(self) -> float:
        if self.balls == 0:
            return 0.0
        return (self.runs / self.balls) * 100


@dataclass
class BowlerSpell:
    """Tracks a bowler's spell"""
    player: Player
    overs: int = 0
    balls: int = 0
    runs: int = 0
    wickets: int = 0
    wides: int = 0
    no_balls: int = 0

    @property
    def overs_display(self) -> str:
        return f"{self.overs}.{self.balls}"

    @property
    def economy(self) -> float:
        total_balls = self.overs * 6 + self.balls
        if total_balls == 0:
            return 0.0
        return (self.runs / total_balls) * 6


@dataclass
class BallOutcome:
    """Result of a single ball — compatible with existing API"""
    runs: int = 0
    is_wicket: bool = False
    is_wide: bool = False
    is_no_ball: bool = False
    is_bye: bool = False
    is_leg_bye: bool = False
    is_boundary: bool = False
    is_six: bool = False
    dismissal_type: str = ""
    commentary: str = ""
    contact_quality: str = ""
    delivery_name: str = ""


@dataclass
class InningsState:
    """Current state of an innings"""
    batting_team: list
    bowling_team: list
    total_runs: int = 0
    wickets: int = 0
    overs: int = 0
    balls: int = 0
    target: Optional[int] = None

    batter_innings: dict = field(default_factory=dict)   # player_id -> BatterInnings
    bowler_spells: dict = field(default_factory=dict)     # player_id -> BowlerSpell

    striker_id: Optional[int] = None
    non_striker_id: Optional[int] = None
    current_bowler_id: Optional[int] = None
    last_bowler_id: Optional[int] = None

    batting_order: list = field(default_factory=list)
    next_batter_index: int = 2

    # Interactive match states
    context: MatchContext = field(default_factory=MatchContext)
    batter_states: dict = field(default_factory=dict)     # player_id -> BatterState
    bowler_states: dict = field(default_factory=dict)     # player_id -> BowlerState
    this_over: list = field(default_factory=list)

    extras: int = 0
    batting_team_id: Optional[int] = None

    # v2 engine additions
    pitch: PitchDNA = field(default_factory=lambda: PITCHES["balanced"])
    is_second_innings: bool = False
    balls_faced: dict = field(default_factory=dict)       # player_id -> int
    bowler_overs_count: dict = field(default_factory=dict) # player_id -> int
    partnership_runs: int = 0

    @property
    def overs_display(self) -> str:
        return f"{self.overs}.{self.balls}"

    @property
    def run_rate(self) -> float:
        total_balls = self.overs * 6 + self.balls
        if total_balls == 0:
            return 0.0
        return (self.total_runs / total_balls) * 6

    @property
    def required_rate(self) -> Optional[float]:
        if self.target is None:
            return None
        remaining = self.target - self.total_runs
        balls_left = (20 * 6) - (self.overs * 6 + self.balls)
        if balls_left <= 0:
            return 99.99
        return (remaining / balls_left) * 6

    @property
    def is_innings_complete(self) -> bool:
        if self.wickets >= 10:
            return True
        if self.overs >= 20:
            return True
        if self.target and self.total_runs >= self.target:
            return True
        return False


# ================================================================
# HELPER FUNCTIONS (ported from POC)
# ================================================================

# --- Stat compression ---
COMPRESS_BASE = 28
COMPRESS_SCALE = 0.45


def compress(rating: float) -> float:
    """Compress a raw 0-100 rating to a narrower effective range."""
    return COMPRESS_BASE + rating * COMPRESS_SCALE


def get_pitch_assist(pitch: PitchDNA, stat_name: str) -> int:
    if stat_name in ("speed_factor", "swing"):
        return pitch.pace_assist
    if stat_name == "bounce":
        return (pitch.pace_assist + pitch.bounce) // 2
    if stat_name in ("turn", "flight"):
        return pitch.spin_assist
    if stat_name == "variation":
        return pitch.spin_assist * 7 // 10
    return 50


def ball_age_modifier(overs_bowled: int, stat_name: str) -> float:
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
    if stat_name == "speed_factor":
        if isinstance(bowler_dna, PacerDNA):
            return bowler_dna.speed_factor()
        return 30
    return getattr(bowler_dna, stat_name, 50)


FATIGUE_MULTIPLIERS = {0: 1.0, 1: 1.0, 2: 0.97, 3: 0.92, 4: 0.85}


def get_fatigue(bowler_overs: int) -> float:
    return FATIGUE_MULTIPLIERS.get(bowler_overs, 0.85)


def get_sigma(overs: int) -> float:
    if overs < 6:
        return 12.0
    if overs < 16:
        return 11.0
    return 14.0


def get_settled_modifier(balls_faced: int) -> float:
    if balls_faced <= 5:
        return -3.0
    if balls_faced <= 15:
        return 0.0
    if balls_faced <= 40:
        return 2.0
    return -1.0


def get_deterioration_mod(pitch: PitchDNA, is_second_innings: bool) -> float:
    if not is_second_innings:
        return 1.0
    return 1.0 + pitch.deterioration / 150


# --- Delivery repertoire ---

def get_repertoire(player: Player) -> List[Delivery]:
    dna = player.bowler_dna
    if dna is None:
        return [PACER_DELIVERIES["good_length"]]

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

    return [PACER_DELIVERIES["good_length"]]


def choose_optimal_delivery(repertoire: List[Delivery], batter: Player) -> Delivery:
    """Captain picks smartly 60% of the time, random 40%."""
    if random.random() < 0.45:
        return random.choice(repertoire)

    batter_dna = batter.batting_dna
    if batter_dna is None:
        return random.choice(repertoire)

    scored = []
    for d in repertoire:
        primary_stat = max(d.batter_weights, key=d.batter_weights.get)
        batter_val = getattr(batter_dna, primary_stat, 50)
        advantage = 50 - batter_val
        scored.append((d, advantage))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_n = scored[:3]
    deliveries = [s[0] for s in top_n]
    weights = [3, 2, 1][:len(deliveries)]
    return random.choices(deliveries, weights=weights)[0]


# --- Core matchup pipeline ---

def execution_check(bowler_dna, delivery: Delivery, pitch: PitchDNA,
                    fatigue: float, overs: int) -> str:
    control = bowler_dna.control * fatigue
    roll = random.gauss(control, 8)

    target = delivery.exec_difficulty
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


def bowler_attack_rating(bowler_dna, delivery: Delivery, pitch: PitchDNA,
                         overs: int, fatigue: float, is_second: bool) -> float:
    rating = 0.0
    for stat_name, weight in delivery.bowler_weights.items():
        base_stat = get_bowler_stat(bowler_dna, stat_name)
        pa = get_pitch_assist(pitch, stat_name)
        if is_second and stat_name in ("turn", "flight"):
            pa = min(100, pa * get_deterioration_mod(pitch, True))
        effective = base_stat * (0.5 + pa * 0.01)
        effective *= ball_age_modifier(overs, stat_name)
        effective *= fatigue
        effective = min(120, effective)
        rating += effective * weight
    return rating


def batter_skill_rating(batter_dna: BatterDNA, delivery: Delivery) -> float:
    rating = 0.0
    for stat_name, weight in delivery.batter_weights.items():
        stat = getattr(batter_dna, stat_name, 50)
        rating += stat * weight
    return rating


def tactical_bonus(batter_dna: BatterDNA, delivery: Delivery) -> float:
    primary = max(delivery.batter_weights, key=delivery.batter_weights.get)
    primary_val = getattr(batter_dna, primary, 50)
    raw = (50 - primary_val) * 0.10
    return max(-3.0, min(3.0, raw))


def calculate_margin(attack: float, skill: float, tac_bonus: float,
                     approach: str, sigma: float) -> float:
    approach_mods = {
        "survive":  (0.70, +3),
        "rotate":   (0.90, +1.5),
        "push":     (1.08, 0),
        "all_out":  (1.25, 0),
    }
    sigma_mult, base_shift = approach_mods.get(approach, (0.90, +1))
    adjusted_sigma = sigma * sigma_mult
    batter_performance = random.gauss(skill + base_shift, adjusted_sigma)
    difficulty = attack + tac_bonus
    return batter_performance - difficulty


def resolve_contact(margin: float) -> str:
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

    return 0, False, False


def resolve_edge(pitch: PitchDNA, catch_modifier: float = 0.0) -> Tuple[bool, str, int]:
    carry = pitch.carry / 100
    catch_chance = 0.25 * carry + catch_modifier
    catch_chance = max(0.05, min(0.50, catch_chance))
    if random.random() < catch_chance:
        dismissal = random.choices(
            ["caught_behind", "caught"],
            weights=[0.55, 0.45]
        )[0]
        return True, dismissal, 0
    return False, "", random.choice([0, 0, 0, 1])


def resolve_clean_beat(margin: float, delivery: Delivery) -> Tuple[bool, str]:
    margin_abs = abs(margin)
    wicket_chance = min(0.95, 0.55 + (margin_abs - 18) * 0.025)
    if random.random() < wicket_chance:
        types = list(delivery.dismissal_weights.keys())
        weights = list(delivery.dismissal_weights.values())
        dismissal = random.choices(types, weights=weights)[0]
        return True, dismissal
    return False, ""


def safety_net(innings: InningsState) -> float:
    total_b = innings.overs * 6 + innings.balls
    if total_b < 6:
        return 0
    rr = innings.run_rate
    if innings.wickets >= 5 and total_b < 36:
        return 15
    if rr < 4.0 and innings.wickets < 8:
        return 12
    if rr > 13:
        return -10
    return 0


# --- Aggression mapping ---

AGGRESSION_MAP = {
    "defend": "survive",
    "balanced": "rotate",
    "attack": "push",
}


def map_aggression(aggression: str, innings: InningsState) -> str:
    """Map API aggression to v2 approach. In death overs with attack, go all_out."""
    if aggression == "attack":
        if innings.overs >= 18:
            return "all_out"
        if innings.target is not None:
            balls_left = (20 * 6) - (innings.overs * 6 + innings.balls)
            if balls_left > 0:
                rrr = ((innings.target - innings.total_runs) / balls_left) * 6
                if rrr > 12:
                    return "all_out"
        if random.random() < 0.20:
            return "all_out"
        return "push"
    return AGGRESSION_MAP.get(aggression, "rotate")


def get_approach_for_situation(innings: InningsState) -> str:
    """AI batting approach based on match situation."""
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
    if overs >= 18:
        return "all_out"
    if overs >= 16:
        return "push"
    return "rotate"


# --- Commentary generator ---

def generate_commentary(batter: Player, bowler: Player, outcome: BallOutcome) -> str:
    """Generate rich commentary from ball outcome."""
    batter_name = batter.name
    bowler_name = bowler.name

    if outcome.is_wide:
        return f"Wide ball from {bowler_name}, 1 run added"
    if outcome.is_no_ball:
        return f"No ball! {outcome.runs} runs"

    if outcome.is_wicket:
        d = outcome.dismissal_type
        if d == "bowled":
            return f"WICKET! {bowler_name} cleans up {batter_name}! The stumps are shattered!"
        elif d == "lbw":
            return f"WICKET! {bowler_name} traps {batter_name} in front! Plumb LBW!"
        elif d == "caught":
            return f"OUT! {batter_name} caught in the deep off {bowler_name}!"
        elif d == "caught_behind":
            return f"OUT! Edge and taken! {batter_name} caught behind off {bowler_name}!"
        elif d == "stumped":
            return f"STUMPED! {batter_name} beaten in the flight by {bowler_name}!"
        elif d == "top_edge":
            return f"OUT! Top edge from {batter_name} off the bouncer, taken at fine leg!"
        elif d == "hit_wicket":
            return f"WICKET! {batter_name} hit wicket trying to pull {bowler_name}!"
        elif d == "run_out":
            return f"RUN OUT! {batter_name} is short of the crease!"
        return f"WICKET! {batter_name} dismissed by {bowler_name}!"

    cq = outcome.contact_quality
    dn = outcome.delivery_name

    if outcome.is_six:
        if cq == "perfect":
            return f"MASSIVE SIX! {batter_name} smashes {bowler_name} into the stands! Perfect connection!"
        return f"SIX! {batter_name} launches it over the boundary off {bowler_name}!"
    if outcome.is_boundary:
        if cq == "perfect":
            return f"FOUR! Perfectly timed by {batter_name}, races to the boundary!"
        if cq == "good":
            return f"FOUR! Beautiful shot by {batter_name} off {bowler_name}!"
        return f"FOUR! {batter_name} finds the gap off {bowler_name}!"

    if outcome.runs == 0:
        if cq == "beaten":
            return f"Beaten! {bowler_name} beats {batter_name} all ends up with the {dn}!"
        if cq == "defended":
            return f"{batter_name} defends solidly."
        return f"Dot ball. {bowler_name} keeps it tight."

    if outcome.runs == 1:
        return f"{batter_name} works it away for a single."
    if outcome.runs == 2:
        return f"Good running! {batter_name} picks up {outcome.runs} runs."
    if outcome.runs == 3:
        return f"Excellent running between the wickets! {outcome.runs} runs."

    return f"{batter_name} gets {outcome.runs} off {bowler_name}."


# ================================================================
# MATCH ENGINE V2 CLASS
# ================================================================

class MatchEngineV2:
    """
    DNA-based T20 match simulation engine.
    Drop-in replacement for MatchEngine (v1).
    """

    def __init__(self):
        self.innings1: Optional[InningsState] = None
        self.innings2: Optional[InningsState] = None
        self.current_innings: Optional[InningsState] = None

    def setup_innings(
        self,
        batting_team: list,
        bowling_team: list,
        target: Optional[int] = None,
        pitch: Optional[PitchDNA] = None,
        is_second_innings: bool = False,
    ) -> InningsState:
        """Initialize an innings with batting order as provided."""
        if pitch is None:
            pitch = PITCHES["balanced"]

        innings = InningsState(
            batting_team=batting_team,
            bowling_team=bowling_team,
            target=target,
            batting_order=[p.id for p in batting_team],
            pitch=pitch,
            is_second_innings=is_second_innings,
        )

        # Set openers
        innings.striker_id = batting_team[0].id
        innings.non_striker_id = batting_team[1].id

        # Initialize batter innings
        innings.batter_innings[batting_team[0].id] = BatterInnings(player=batting_team[0])
        innings.batter_innings[batting_team[1].id] = BatterInnings(player=batting_team[1])

        # Initialize balls_faced
        innings.balls_faced[batting_team[0].id] = 0
        innings.balls_faced[batting_team[1].id] = 0

        return innings

    def _simulate_ball_v2(
        self,
        batter: Player,
        bowler: Player,
        innings: InningsState,
        approach: str = "rotate",
        delivery_type: str = None,
    ) -> BallOutcome:
        """Full v2 pipeline: jaffa → execution → matchup → compression → Gaussian → resolve."""
        overs = innings.overs
        batter_dna = batter.batting_dna
        bowler_dna = bowler.bowler_dna

        # Fallback DNA for players without DNA (shouldn't happen with updated generator)
        if batter_dna is None:
            batter_dna = BatterDNA(
                vs_pace=max(20, batter.batting - 10),
                vs_bounce=max(20, batter.batting - 15),
                vs_spin=max(20, batter.batting - 10),
                vs_deception=max(20, batter.batting - 20),
                off_side=max(20, batter.batting - 10),
                leg_side=max(20, batter.batting - 10),
                power=batter.power,
            )
        if bowler_dna is None:
            # Fallback: create a basic pacer DNA from bowling attr
            bowler_dna = PacerDNA(
                speed=130,
                swing=max(20, batter.bowling - 10) if hasattr(bowler, 'bowling') else 40,
                bounce=40,
                control=max(30, bowler.bowling) if hasattr(bowler, 'bowling') else 50,
            )

        bowler_overs = innings.bowler_overs_count.get(bowler.id, 0)
        fatigue = get_fatigue(bowler_overs)
        sigma = get_sigma(overs)

        # Get delivery repertoire and choose (or use user-selected delivery)
        repertoire = get_repertoire(bowler)
        if delivery_type:
            # User selected a specific delivery — find it in repertoire or all deliveries
            all_deliveries = {**PACER_DELIVERIES, **SPINNER_DELIVERIES}
            delivery = all_deliveries.get(delivery_type)
            if delivery is None or delivery not in repertoire:
                delivery = choose_optimal_delivery(repertoire, batter)
        else:
            delivery = choose_optimal_delivery(repertoire, batter)

        outcome = BallOutcome(delivery_name=delivery.name)

        # Step 0: Jaffa — increases with balls faced
        bf = innings.balls_faced.get(batter.id, 0)
        jaffa_rate = 0.005 + max(0, bf - 20) * 0.0028
        if random.random() < jaffa_rate:
            outcome.is_wicket = True
            outcome.contact_quality = "clean_beat"
            types = list(delivery.dismissal_weights.keys())
            weights = list(delivery.dismissal_weights.values())
            outcome.dismissal_type = random.choices(types, weights=weights)[0]
            outcome.commentary = generate_commentary(batter, bowler, outcome)
            return outcome

        # Step 1: Execution check
        exec_result = execution_check(bowler_dna, delivery, innings.pitch, fatigue, overs)
        if exec_result == "bad_miss":
            batter_bonus = random.uniform(12, 18)
        elif exec_result == "slight_miss":
            batter_bonus = random.uniform(4, 10)
        else:
            batter_bonus = 0

        # Step 2: Bowler attack rating
        raw_attack = bowler_attack_rating(bowler_dna, delivery, innings.pitch, overs,
                                          fatigue, innings.is_second_innings)

        # Step 3: Batter skill rating
        raw_skill = batter_skill_rating(batter_dna, delivery) + batter_bonus

        # Tail-ender floor: only for genuinely weak batters (avg DNA < 40)
        if batter_dna.avg() < 40:
            raw_skill = max(raw_skill, 63)

        # Settled modifier
        raw_skill += get_settled_modifier(bf)

        # Safety net
        raw_skill += safety_net(innings)

        # Step 4: Compress both ratings
        compressed_skill = compress(raw_skill)
        compressed_attack = compress(raw_attack)

        # Step 5: Tactical bonus
        tac = tactical_bonus(batter_dna, delivery)

        # Step 6: Gaussian margin
        margin = calculate_margin(compressed_attack, compressed_skill, tac, approach, sigma)

        # Step 7: Resolve contact
        contact = resolve_contact(margin)
        outcome.contact_quality = contact

        if contact in ("perfect", "good", "decent", "defended"):
            runs, is_boundary, is_six = resolve_runs(
                contact, batter_dna.power, margin, innings.pitch, approach
            )
            outcome.runs = runs
            outcome.is_boundary = is_boundary
            outcome.is_six = is_six
        elif contact == "beaten":
            outcome.runs = 0
        elif contact == "edge":
            is_w, dism, runs = resolve_edge(innings.pitch)
            outcome.is_wicket = is_w
            outcome.dismissal_type = dism
            outcome.runs = runs
        elif contact == "clean_beat":
            is_w, dism = resolve_clean_beat(margin, delivery)
            outcome.is_wicket = is_w
            outcome.dismissal_type = dism
            outcome.runs = 0

        outcome.commentary = generate_commentary(batter, bowler, outcome)
        return outcome

    def calculate_ball_outcome(
        self,
        batter: Player,
        bowler: Player,
        aggression: str,
        innings_state: InningsState,
        delivery_type: str = None,
    ) -> BallOutcome:
        """API-compatible ball calculation — maps aggression and delegates to v2 pipeline."""
        approach = map_aggression(aggression, innings_state)
        return self._simulate_ball_v2(batter, bowler, innings_state, approach, delivery_type=delivery_type)

    def _simulate_ball(
        self,
        batter: Player,
        bowler: Player,
        innings_state: InningsState,
        fielders: list,
        aggression: str = "balanced",
        delivery_type: str = None,
    ) -> BallOutcome:
        """Drop-in replacement for v1's _simulate_ball (called by match.py play_ball)."""
        # Check extras first
        bowler_dna = bowler.bowler_dna
        bowler_overs = innings_state.bowler_overs_count.get(bowler.id, 0)
        fatigue = get_fatigue(bowler_overs)

        if bowler_dna is not None:
            eff_ctrl = bowler_dna.control * fatigue
        else:
            eff_ctrl = max(30, bowler.bowling) * fatigue

        wide_chance = max(0.015, 0.06 - eff_ctrl * 0.0004)
        extra_roll = random.random()

        if extra_roll < wide_chance:
            return BallOutcome(
                runs=1,
                is_wide=True,
                commentary=f"Wide ball from {bowler.name}, 1 run added"
            )
        if extra_roll < wide_chance + 0.008:
            runs = random.choices([0, 1, 2, 4, 6], weights=[30, 30, 10, 20, 10])[0]
            return BallOutcome(
                runs=runs + 1,
                is_no_ball=True,
                is_boundary=runs >= 4,
                is_six=runs == 6,
                commentary=f"No ball! {runs + 1} runs"
            )

        return self.calculate_ball_outcome(batter, bowler, aggression, innings_state, delivery_type=delivery_type)

    def select_bowler(self, innings: InningsState) -> Player:
        """Select next bowler (cannot be same as last over, max 4 overs)."""
        bowlers = [p for p in innings.bowling_team
                   if _get_role_str(p) in _BOWLER_ROLES]

        available = []
        for b in bowlers:
            overs_bowled = innings.bowler_overs_count.get(b.id, 0)
            if overs_bowled >= 4:
                continue
            if b.id == innings.last_bowler_id:
                continue
            available.append(b)

        if not available:
            available = [b for b in bowlers if b.id != innings.last_bowler_id]
        if not available:
            available = bowlers
        if not available:
            # Fallback: any player from bowling team
            available = innings.bowling_team

        # Weight by bowler DNA avg, fallback to bowling attr
        weights = []
        for b in available:
            dna = b.bowler_dna
            if dna is not None:
                weights.append(dna.avg())
            else:
                weights.append(max(10, b.bowling))
        return random.choices(available, weights=weights)[0]

    def simulate_over(self, innings: InningsState, aggression: str = "balanced") -> list:
        """Simulate a single over."""
        outcomes = []
        balls_bowled = 0
        wickets_this_over = 0

        # Use existing bowler if set, otherwise auto-select
        if innings.current_bowler_id:
            bowler = next(p for p in innings.bowling_team if p.id == innings.current_bowler_id)
        else:
            bowler = self.select_bowler(innings)
            innings.current_bowler_id = bowler.id

        # Initialize states
        if bowler.id not in innings.bowler_states:
            innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)
        if bowler.id not in innings.bowler_spells:
            innings.bowler_spells[bowler.id] = BowlerSpell(player=bowler)

        fielders = [p for p in innings.bowling_team if p.id != bowler.id]
        innings.this_over = []

        while balls_bowled < 6 and not innings.is_innings_complete:
            striker = next(p for p in innings.batting_team if p.id == innings.striker_id)

            outcome = self._simulate_ball(striker, bowler, innings, fielders, aggression)
            outcomes.append(outcome)
            innings.this_over.append(outcome)

            # Update states
            if not outcome.is_wide and not outcome.is_no_ball:
                balls_bowled += 1
                innings.balls += 1

                # Update batter
                batter_innings = innings.batter_innings[striker.id]
                batter_innings.balls += 1
                batter_innings.runs += outcome.runs
                if outcome.is_boundary and not outcome.is_six:
                    batter_innings.fours += 1
                if outcome.is_six:
                    batter_innings.sixes += 1

                # Update batter state
                b_state = innings.batter_states.setdefault(
                    striker.id, BatterState(player_id=striker.id)
                )
                b_state.balls_faced += 1
                b_state.is_settled = b_state.balls_faced > 15

                # Track balls faced for jaffa rate
                innings.balls_faced[striker.id] = innings.balls_faced.get(striker.id, 0) + 1

                # On-fire check
                if outcome.is_boundary:
                    b_state.recent_outcomes.append("4/6")
                else:
                    b_state.recent_outcomes.append("other")
                if len(b_state.recent_outcomes) >= 3:
                    recent_3 = b_state.recent_outcomes[-3:]
                    b_state.is_on_fire = recent_3.count("4/6") >= 2

            # Update bowler spell
            spell = innings.bowler_spells[bowler.id]
            if outcome.is_wide:
                spell.wides += 1
                spell.runs += 1
                innings.extras += 1
            elif outcome.is_no_ball:
                spell.no_balls += 1
                spell.runs += outcome.runs
                innings.extras += 1
            else:
                spell.runs += outcome.runs

            innings.total_runs += outcome.runs
            innings.partnership_runs += outcome.runs
            innings.context.partnership_runs += outcome.runs

            # Handle wicket — cap at 3 per over
            if outcome.is_wicket:
                if wickets_this_over >= 3:
                    outcome.is_wicket = False
                    outcome.runs = 0
                    outcome.dismissal_type = ""
                    outcome.commentary = f"{striker.name} survives a close call!"
                else:
                    wickets_this_over += 1
                    innings.wickets += 1
                    batter_innings = innings.batter_innings[innings.striker_id]
                    batter_innings.is_out = True
                    batter_innings.dismissal = outcome.dismissal_type
                    batter_innings.bowler = bowler

                    spell.wickets += 1
                    innings.bowler_states[bowler.id].has_confidence = True
                    innings.partnership_runs = 0
                    innings.context.partnership_runs = 0

                    # Bring in next batter
                    if innings.next_batter_index < len(innings.batting_order):
                        next_batter_id = innings.batting_order[innings.next_batter_index]
                        next_batter = next(p for p in innings.batting_team if p.id == next_batter_id)
                        innings.striker_id = next_batter_id
                        innings.batter_innings[next_batter_id] = BatterInnings(player=next_batter)
                        innings.batter_states[next_batter_id] = BatterState(player_id=next_batter_id)
                        innings.balls_faced[next_batter_id] = 0
                        innings.next_batter_index += 1

            # Rotate strike on odd runs
            if not outcome.is_wicket and outcome.runs % 2 == 1:
                innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id

            # End of over
            if innings.balls >= 6:
                innings.overs += 1
                innings.balls = 0
                spell.overs += 1
                spell.balls = 0
                innings.last_bowler_id = bowler.id
                innings.current_bowler_id = None

                # Track bowler overs
                innings.bowler_overs_count[bowler.id] = innings.bowler_overs_count.get(bowler.id, 0) + 1

                # Update bowler state
                innings.bowler_states[bowler.id].consecutive_overs += 1
                innings.bowler_states[bowler.id].is_tired = innings.bowler_states[bowler.id].consecutive_overs > 4

                # Rotate strike at end of over
                innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id
                break

        return outcomes

    def simulate_innings(self, innings: InningsState) -> InningsState:
        """Simulate a complete innings."""
        while not innings.is_innings_complete:
            self.simulate_over(innings)
        return innings

    def simulate_match(
        self,
        team1_players: list,
        team2_players: list,
        team1_bats_first: bool = True,
        pitch: Optional[PitchDNA] = None,
    ) -> dict:
        """Simulate a complete T20 match."""
        if pitch is None:
            pitch = random.choice(list(PITCHES.values()))

        if team1_bats_first:
            first_batting = team1_players
            second_batting = team2_players
        else:
            first_batting = team2_players
            second_batting = team1_players

        # First innings
        self.innings1 = self.setup_innings(first_batting, second_batting, pitch=pitch)
        self.innings1 = self.simulate_innings(self.innings1)

        # Second innings
        target = self.innings1.total_runs + 1
        self.innings2 = self.setup_innings(
            second_batting, first_batting,
            target=target, pitch=pitch, is_second_innings=True
        )
        self.innings2 = self.simulate_innings(self.innings2)

        # Determine result
        if self.innings2.total_runs >= target:
            winner = "team2" if team1_bats_first else "team1"
            margin = f"{10 - self.innings2.wickets} wickets"
            balls_remaining = (20 * 6) - (self.innings2.overs * 6 + self.innings2.balls)
            if balls_remaining > 0:
                margin += f" ({balls_remaining} balls remaining)"
        elif self.innings2.total_runs < target - 1:
            winner = "team1" if team1_bats_first else "team2"
            margin = f"{(target - 1) - self.innings2.total_runs} runs"
        else:
            winner = "tie"
            margin = "Match tied!"

        return {
            "innings1": {
                "runs": self.innings1.total_runs,
                "wickets": self.innings1.wickets,
                "overs": self.innings1.overs_display,
                "run_rate": round(self.innings1.run_rate, 2),
            },
            "innings2": {
                "runs": self.innings2.total_runs,
                "wickets": self.innings2.wickets,
                "overs": self.innings2.overs_display,
                "run_rate": round(self.innings2.run_rate, 2),
            },
            "winner": winner,
            "margin": margin,
        }
