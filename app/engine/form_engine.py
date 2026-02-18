"""
Player Form Engine — Dynamic form updates based on match performance.

Form is a 0.7-1.3 multiplier that affects raw_skill and raw_attack in
the match engine. It modulates the compressed-Gaussian simulation system
where a 1.3x advantage translates to ~+13 effective skill points on
the ~28-73 compressed range — significant but not game-breaking.
"""


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _get_role_str(player) -> str:
    """Get role as string from Player (handles both enum and string)."""
    role = player.role
    return role.value if hasattr(role, 'value') else str(role)


def calculate_form_delta(player, match_stats) -> float:
    """
    Calculate form change after a match.

    Parameters:
        player: Player model instance
        match_stats: PlayerMatchStats (or any object with the batting/bowling fields)

    Returns:
        Form delta in range roughly [-0.08, +0.08].
        Combined with mean reversion, total delta per match is bounded.
    """
    delta = 0.0
    role = _get_role_str(player)

    # --- Batting component ---
    if match_stats.balls_faced > 0:
        sr = (match_stats.runs_scored / match_stats.balls_faced) * 100

        # Par performance: 25 runs at 130 SR is "average" for T20
        run_factor = (match_stats.runs_scored - 25) / 40  # +1 at 65 runs, -0.625 at 0 runs
        sr_factor = (sr - 130) / 100  # Bonus/penalty for strike rate

        batting_delta = _clamp((run_factor * 0.6 + sr_factor * 0.4) * 0.05, -0.06, 0.06)

        # Weight by role
        if role in ('batsman', 'wicket_keeper'):
            delta += batting_delta * 1.0
        elif role == 'all_rounder':
            delta += batting_delta * 0.5
        else:  # bowler
            delta += batting_delta * 0.2

    # --- Bowling component ---
    if match_stats.overs_bowled > 0:
        economy = match_stats.runs_conceded / match_stats.overs_bowled
        wickets = match_stats.wickets_taken

        # Par: economy < 8.0 is good, 1 wicket is neutral
        econ_factor = (8.0 - economy) / 4.0  # +1 at econ 4, -1 at econ 12
        wicket_factor = (wickets - 1) / 2.0  # +1 at 3 wkts, 0 at 1 wkt

        bowling_delta = _clamp((wicket_factor * 0.6 + econ_factor * 0.4) * 0.05, -0.06, 0.06)

        if role == 'bowler':
            delta += bowling_delta * 1.0
        elif role == 'all_rounder':
            delta += bowling_delta * 0.5
        else:
            delta += bowling_delta * 0.2

    # --- Mean reversion ---
    # Pull form back toward 1.0 by 15% per match (prevents runaway streaks)
    current_form = getattr(player, 'form', 1.0)
    reversion = (1.0 - current_form) * 0.15
    delta += reversion

    # --- DNP (Did Not Participate) ---
    # If player was in XI but didn't bat or bowl meaningfully, just revert
    if match_stats.balls_faced == 0 and match_stats.overs_bowled == 0:
        delta = (1.0 - current_form) * 0.10

    return delta


def update_player_form(player, delta: float):
    """Apply form delta and clamp to [0.7, 1.3]."""
    current = getattr(player, 'form', 1.0)
    player.form = _clamp(current + delta, 0.7, 1.3)


def get_form_label(form: float) -> str:
    """Human-readable form label."""
    if form >= 1.15:
        return "Hot"
    elif form >= 1.05:
        return "In Form"
    elif form >= 0.95:
        return "Normal"
    elif form >= 0.85:
        return "Cold"
    else:
        return "Poor"
