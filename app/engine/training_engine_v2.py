"""
Training Engine v2 — Persistent training plans with permanent skill improvement.

On each training day, all players with a TrainingPlan get permanent DNA/attribute gains
based on their configured focus area. Gains diminish as attributes approach their cap.
"""
import json
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.career import TrainingPlan, TrainingLog, TrainingFocus
from app.models.player import Player, PlayerRole
from app.engine.dna import BatterDNA, PacerDNA, SpinnerDNA, bowler_dna_from_dict


# ─── Focus Configuration ────────────────────────────────────────────────────
# Maps each TrainingFocus value to its target DNA/attribute and metadata.

TRAINING_FOCUS_CONFIG: Dict[str, dict] = {
    # === Batting focuses (BatterDNA) ===
    "vs_pace": {
        "display_name": "Pace Handling",
        "description": "Improve batting technique against pace bowlers",
        "target_type": "batting_dna",
        "target_attributes": ["vs_pace"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "zap",
    },
    "vs_spin": {
        "display_name": "Spin Handling",
        "description": "Improve batting technique against spin bowlers",
        "target_type": "batting_dna",
        "target_attributes": ["vs_spin"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "rotate-ccw",
    },
    "vs_bounce": {
        "display_name": "Short Ball Handling",
        "description": "Improve ability to handle short-pitched deliveries",
        "target_type": "batting_dna",
        "target_attributes": ["vs_bounce"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "trending-up",
    },
    "shot_selection": {
        "display_name": "Shot Selection",
        "description": "Improve judgment against deceptive deliveries",
        "target_type": "batting_dna",
        "target_attributes": ["vs_deception"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "eye",
    },
    "power_hitting": {
        "display_name": "Power Hitting",
        "description": "Improve six-hitting ability and bat speed",
        "target_type": "batting_dna",
        "target_attributes": ["power"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder"],
        "icon": "flame",
    },
    "off_side_play": {
        "display_name": "Off-Side Play",
        "description": "Improve drives and cuts through the off side",
        "target_type": "batting_dna",
        "target_attributes": ["off_side"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "arrow-right",
    },
    "leg_side_play": {
        "display_name": "Leg-Side Play",
        "description": "Improve flicks, pulls, and sweeps through leg side",
        "target_type": "batting_dna",
        "target_attributes": ["leg_side"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "all_rounder", "wicket_keeper"],
        "icon": "arrow-left",
    },
    # === Bowling focuses (PacerDNA / SpinnerDNA) ===
    "pace_bowling": {
        "display_name": "Pace Development",
        "description": "Increase bowling speed and swing movement",
        "target_type": "bowler_dna",
        "target_attributes": ["speed", "swing"],
        "base_improvement": 0.8,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "zap",
        "pacer_only": True,
    },
    "swing_bowling": {
        "display_name": "Swing Mastery",
        "description": "Improve ability to swing the ball both ways",
        "target_type": "bowler_dna",
        "target_attributes": ["swing"],
        "base_improvement": 1.0,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "wind",
        "pacer_only": True,
    },
    "bounce_extraction": {
        "display_name": "Bounce Extraction",
        "description": "Improve ability to extract steep bounce from the pitch",
        "target_type": "bowler_dna",
        "target_attributes": ["bounce"],
        "base_improvement": 1.0,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "trending-up",
        "pacer_only": True,
    },
    "spin_mastery": {
        "display_name": "Spin Development",
        "description": "Improve turn and flight on spin deliveries",
        "target_type": "bowler_dna",
        "target_attributes": ["turn", "flight"],
        "base_improvement": 0.8,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "rotate-ccw",
        "spinner_only": True,
    },
    "bowling_variation": {
        "display_name": "Bowling Variations",
        "description": "Develop new deliveries and improve variation",
        "target_type": "bowler_dna",
        "target_attributes": ["variation"],
        "base_improvement": 1.0,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "shuffle",
    },
    "bowling_control": {
        "display_name": "Bowling Accuracy",
        "description": "Improve line, length, and overall bowling control",
        "target_type": "bowler_dna",
        "target_attributes": ["control"],
        "base_improvement": 1.0,
        "best_for_roles": ["bowler", "all_rounder"],
        "icon": "target",
    },
    # === General (Player attributes) ===
    "fitness": {
        "display_name": "Fitness Training",
        "description": "Improve stamina and injury resistance",
        "target_type": "player_attr",
        "target_attributes": ["fitness"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "bowler", "all_rounder", "wicket_keeper"],
        "icon": "heart",
    },
    "fielding": {
        "display_name": "Fielding Drills",
        "description": "Improve catching, ground fielding, and throwing",
        "target_type": "player_attr",
        "target_attributes": ["fielding"],
        "base_improvement": 1.0,
        "best_for_roles": ["batsman", "bowler", "all_rounder", "wicket_keeper"],
        "icon": "shield",
    },
}


def calculate_improvement(current_value: int, base_improvement: float, player_age: int, is_speed: bool = False) -> float:
    """
    Calculate the actual improvement considering diminishing returns and age.

    For DNA attributes (0-99 scale):
      gain = base * (1 - current / 120) * age_factor
      Floor: 0.2 per session

    For PacerDNA.speed (120-155 kph scale):
      gain = base * (1 - (current - 120) / 50) * age_factor
      Floor: 0.2 kph per session
    """
    if is_speed:
        # Speed: 120-155 kph range
        diminishing = max(0.1, 1.0 - (current_value - 120) / 50.0)
    else:
        # Standard 0-99 range
        diminishing = max(0.17, 1.0 - current_value / 120.0)

    if player_age < 25:
        age_factor = 1.2
    elif player_age <= 30:
        age_factor = 1.0
    elif player_age <= 34:
        age_factor = 0.8
    else:
        age_factor = 0.6

    gain = base_improvement * diminishing * age_factor
    return max(0.2, round(gain, 1))


def process_training_day(db: Session, career_id: int, game_day_id: int) -> List[dict]:
    """
    Auto-train all players who have a TrainingPlan.
    Called when advance_day() lands on a training day.

    Returns list of improvements:
    [{"player_id", "player_name", "focus", "attribute", "old", "new", "gain"}]
    """
    plans = db.query(TrainingPlan).filter_by(career_id=career_id).all()

    improvements = []
    for plan in plans:
        player = db.query(Player).get(plan.player_id)
        if not player:
            continue

        config = TRAINING_FOCUS_CONFIG.get(plan.focus.value)
        if not config:
            continue

        target_type = config["target_type"]

        for attr_name in config["target_attributes"]:
            result = _apply_improvement(player, target_type, attr_name, config["base_improvement"])
            if result is None:
                continue

            old_val, new_val, gain = result

            improvements.append({
                "player_id": player.id,
                "player_name": player.name,
                "focus": plan.focus.value,
                "attribute": attr_name,
                "old": old_val,
                "new": new_val,
                "gain": gain,
            })

            db.add(TrainingLog(
                career_id=career_id,
                game_day_id=game_day_id,
                player_id=player.id,
                focus=plan.focus.value,
                attribute_improved=attr_name,
                old_value=old_val,
                new_value=new_val,
                improvement=gain,
            ))

    db.flush()
    return improvements


def _apply_improvement(
    player: Player,
    target_type: str,
    attr_name: str,
    base_improvement: float,
) -> Optional[tuple]:
    """
    Apply a single attribute improvement to a player.
    Returns (old_value, new_value, gain) or None if not applicable.
    """
    if target_type == "batting_dna":
        dna = player.batting_dna
        if not dna:
            return None
        current = getattr(dna, attr_name, None)
        if current is None:
            return None

        gain = calculate_improvement(current, base_improvement, player.age)
        new_val = min(99, round(current + gain))
        if new_val == current:
            new_val = min(99, current + 1)  # Guarantee at least +1 if not at cap
        if current >= 99:
            return None

        setattr(dna, attr_name, new_val)
        player.batting_dna_json = json.dumps(dna.to_dict())
        return (current, new_val, round(new_val - current, 1))

    elif target_type == "bowler_dna":
        dna = player.bowler_dna
        if not dna:
            return None

        is_speed = attr_name == "speed"
        current = getattr(dna, attr_name, None)
        if current is None:
            return None

        cap = 155 if is_speed else 99
        if current >= cap:
            return None

        gain = calculate_improvement(current, base_improvement, player.age, is_speed=is_speed)
        new_val = min(cap, round(current + gain))
        if new_val == current:
            new_val = min(cap, current + 1)

        setattr(dna, attr_name, new_val)
        player.bowler_dna_json = json.dumps(dna.to_dict())
        return (current, new_val, round(new_val - current, 1))

    elif target_type == "player_attr":
        current = getattr(player, attr_name, None)
        if current is None:
            return None
        if current >= 100:
            return None

        gain = calculate_improvement(current, base_improvement, player.age)
        new_val = min(100, round(current + gain))
        if new_val == current:
            new_val = min(100, current + 1)

        setattr(player, attr_name, new_val)
        return (current, new_val, round(new_val - current, 1))

    return None


def get_focus_options_for_player(player: Player) -> List[str]:
    """Get valid training focus options for a player based on their DNA and role."""
    options = []
    for focus_key, config in TRAINING_FOCUS_CONFIG.items():
        target_type = config["target_type"]

        if target_type == "batting_dna":
            if player.batting_dna is not None:
                options.append(focus_key)
        elif target_type == "bowler_dna":
            dna = player.bowler_dna
            if dna is None:
                continue
            if config.get("pacer_only") and isinstance(dna, SpinnerDNA):
                continue
            if config.get("spinner_only") and isinstance(dna, PacerDNA):
                continue
            options.append(focus_key)
        elif target_type == "player_attr":
            options.append(focus_key)

    return options
