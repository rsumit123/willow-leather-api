"""
Training Engine — Apply/expire training boosts around matches.

Before a match: apply active boosts to player attributes.
After a match: decrement matches_remaining and expire spent boosts.
"""
import json
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session

from app.models.career import TrainingSession
from app.models.player import Player


def get_active_boosts_for_team(
    db: Session, career_id: int, team_id: int
) -> Dict[int, List[dict]]:
    """
    Get all active training boosts for a team's players.

    Returns: {player_id: [{"attribute": str, "amount": int}, ...]}
    """
    active = db.query(TrainingSession).filter(
        TrainingSession.career_id == career_id,
        TrainingSession.matches_remaining > 0,
    ).all()

    boosts = {}
    for session in active:
        player_ids = json.loads(session.player_ids_json)
        for pid in player_ids:
            if pid not in boosts:
                boosts[pid] = []
            boosts[pid].append({
                "attribute": session.boost_attribute,
                "amount": session.boost_amount,
            })

    return boosts


def apply_boosts_to_player(player: Player, boosts: List[dict]) -> Dict[str, int]:
    """
    Temporarily boost a player's attributes for a match.
    Returns dict of original values so they can be restored.

    Boost attributes map:
    - "batting" -> player.batting
    - "bowling" -> player.bowling
    - "fielding" -> player.fielding
    - "fitness" -> player.fitness
    - "vs_spin", "vs_pace", "power", "control" -> DNA attributes
    """
    originals = {}

    for boost in boosts:
        attr = boost["attribute"]
        amount = boost["amount"]

        # Direct player attributes
        if attr in ("batting", "bowling", "fielding", "fitness"):
            originals[attr] = getattr(player, attr)
            setattr(player, attr, min(100, getattr(player, attr) + amount))
        # Power (direct attribute)
        elif attr == "power" and hasattr(player, "power"):
            originals["power"] = player.power
            player.power = min(100, player.power + amount)

    return originals


def restore_player_attributes(player: Player, originals: Dict[str, int]):
    """Restore player attributes after match simulation."""
    for attr, value in originals.items():
        setattr(player, attr, value)


def decrement_boosts_after_match(db: Session, career_id: int):
    """
    Decrement matches_remaining on all active boosts.
    Called after each match is played.
    """
    active = db.query(TrainingSession).filter(
        TrainingSession.career_id == career_id,
        TrainingSession.matches_remaining > 0,
    ).all()

    for session in active:
        session.matches_remaining -= 1

    db.flush()
