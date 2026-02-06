"""
Delivery definitions for Match Engine v2.
Each delivery has bowler/batter stat weights and dismissal profiles.
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Delivery:
    name: str
    bowler_weights: Dict[str, float]
    batter_weights: Dict[str, float]
    exec_difficulty: int
    dismissal_weights: Dict[str, float] = field(default_factory=dict)


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
