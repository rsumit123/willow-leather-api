"""
Delivery definitions for Match Engine v2.
Each delivery has bowler/batter stat weights and dismissal profiles.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Delivery:
    name: str
    display_name: str
    description: str
    bowler_weights: Dict[str, float]
    batter_weights: Dict[str, float]
    exec_difficulty: int
    dismissal_weights: Dict[str, float] = field(default_factory=dict)
    # Which batter DNA stat this delivery primarily targets (for matchup hints)
    targets_stat: Optional[str] = None


PACER_DELIVERIES = {
    "good_length": Delivery(
        name="good_length",
        display_name="Good Length",
        description="Standard delivery, tests technique",
        bowler_weights={"control": 0.4, "swing": 0.3, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.7, "off_side": 0.3},
        exec_difficulty=30,
        dismissal_weights={"bowled": 0.25, "lbw": 0.20, "caught": 0.35, "caught_behind": 0.20},
        targets_stat="vs_pace",
    ),
    "outswinger": Delivery(
        name="outswinger",
        display_name="Outswinger",
        description="Swings away from the batter, seeks the edge",
        bowler_weights={"swing": 0.6, "control": 0.4},
        batter_weights={"vs_pace": 0.6, "off_side": 0.4},
        exec_difficulty=42,
        dismissal_weights={"caught_behind": 0.40, "caught": 0.30, "bowled": 0.20, "lbw": 0.10},
        targets_stat="vs_pace",
    ),
    "inswinger": Delivery(
        name="inswinger",
        display_name="Inswinger",
        description="Swings into the batter, targets pads and stumps",
        bowler_weights={"swing": 0.6, "control": 0.4},
        batter_weights={"vs_pace": 0.5, "leg_side": 0.5},
        exec_difficulty=45,
        dismissal_weights={"lbw": 0.40, "bowled": 0.40, "caught": 0.15, "caught_behind": 0.05},
        targets_stat="vs_pace",
    ),
    "bouncer": Delivery(
        name="bouncer",
        display_name="Bouncer",
        description="Short pitched, targets the body and gloves",
        bowler_weights={"bounce": 0.5, "speed_factor": 0.5},
        batter_weights={"vs_bounce": 0.6, "leg_side": 0.4},
        exec_difficulty=38,
        dismissal_weights={"caught": 0.55, "top_edge": 0.25, "bowled": 0.10, "hit_wicket": 0.10},
        targets_stat="vs_bounce",
    ),
    "yorker": Delivery(
        name="yorker",
        display_name="Yorker",
        description="Full and fast at the base of stumps, hard to execute",
        bowler_weights={"control": 0.7, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.3, "power": 0.3, "leg_side": 0.4},
        exec_difficulty=58,
        dismissal_weights={"bowled": 0.50, "lbw": 0.35, "caught": 0.15},
        targets_stat="vs_pace",
    ),
    "slower_ball": Delivery(
        name="slower_ball",
        display_name="Slower Ball",
        description="Change of pace, deceives the batter's timing",
        bowler_weights={"control": 0.5, "speed_factor": 0.5},
        batter_weights={"vs_deception": 0.7, "power": 0.3},
        exec_difficulty=48,
        dismissal_weights={"caught": 0.55, "bowled": 0.25, "lbw": 0.20},
        targets_stat="vs_deception",
    ),
    "wide_yorker": Delivery(
        name="wide_yorker",
        display_name="Wide Yorker",
        description="Yorker outside off, hard to score and hard to bowl",
        bowler_weights={"control": 0.7, "speed_factor": 0.3},
        batter_weights={"vs_pace": 0.3, "off_side": 0.7},
        exec_difficulty=55,
        dismissal_weights={"bowled": 0.40, "caught_behind": 0.35, "caught": 0.25},
        targets_stat="off_side",
    ),
}

SPINNER_DELIVERIES = {
    "stock_ball": Delivery(
        name="stock_ball",
        display_name="Stock Ball",
        description="Regular spinning delivery, consistent line and length",
        bowler_weights={"turn": 0.5, "control": 0.5},
        batter_weights={"vs_spin": 0.7, "off_side": 0.3},
        exec_difficulty=28,
        dismissal_weights={"bowled": 0.25, "stumped": 0.25, "caught": 0.25, "lbw": 0.15, "caught_behind": 0.10},
        targets_stat="vs_spin",
    ),
    "flighted": Delivery(
        name="flighted",
        display_name="Flighted",
        description="Tossed up with extra flight, invites the drive",
        bowler_weights={"flight": 0.6, "turn": 0.4},
        batter_weights={"vs_spin": 0.4, "vs_deception": 0.3, "power": 0.3},
        exec_difficulty=40,
        dismissal_weights={"stumped": 0.35, "caught": 0.35, "bowled": 0.15, "lbw": 0.15},
        targets_stat="vs_deception",
    ),
    "arm_ball": Delivery(
        name="arm_ball",
        display_name="Arm Ball",
        description="Goes straight on instead of turning, deceives the batter",
        bowler_weights={"variation": 0.7, "control": 0.3},
        batter_weights={"vs_deception": 0.8, "vs_spin": 0.2},
        exec_difficulty=52,
        dismissal_weights={"bowled": 0.40, "lbw": 0.30, "stumped": 0.15, "caught": 0.15},
        targets_stat="vs_deception",
    ),
    "flat_quick": Delivery(
        name="flat_quick",
        display_name="Flat Quick",
        description="Fired in flat and fast, limits scoring options",
        bowler_weights={"control": 0.7, "turn": 0.3},
        batter_weights={"power": 0.5, "vs_spin": 0.5},
        exec_difficulty=32,
        dismissal_weights={"caught": 0.40, "bowled": 0.30, "lbw": 0.20, "stumped": 0.10},
        targets_stat="vs_spin",
    ),
    "wide_of_off": Delivery(
        name="wide_of_off",
        display_name="Wide of Off",
        description="Pitched outside off stump, tempts the cut and drive",
        bowler_weights={"control": 0.6, "turn": 0.4},
        batter_weights={"off_side": 0.6, "vs_spin": 0.4},
        exec_difficulty=38,
        dismissal_weights={"caught": 0.35, "stumped": 0.30, "caught_behind": 0.25, "bowled": 0.10},
        targets_stat="off_side",
    ),
}
