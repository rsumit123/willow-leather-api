"""
Progression Engine — Season-end evaluation, reputation, promotion/sacking.

Called after a season completes. Evaluates board objectives, adjusts reputation,
determines if the user is promoted, sacked, or stays at the same tier.
"""
from sqlalchemy.orm import Session

from app.models.career import (
    Career, Season, BoardObjective, Notification, NotificationType,
    CareerStatus, SeasonPhase, TeamSeasonStats,
)
from app.engine.tier_config import TIER_CONFIG

TIER_ORDER = ["district", "state", "ipl"]

# Reputation adjustments based on performance
REPUTATION_CHANGES = {
    "win_trophy": 25,
    "reach_final": 15,
    "top_4": 5,
    "bottom_half": -10,
    "last_place": -20,
}


def evaluate_season_end(db: Session, career: Career, season: Season) -> dict:
    """
    Evaluate the completed season and determine outcomes.

    Returns a dict summarizing what happened:
    {
        "objectives_met": [...],
        "reputation_change": int,
        "new_reputation": int,
        "promotion_available": bool,
        "sacked": bool,
        "result": "promoted" | "sacked" | "stay",
        "notifications": [...],
    }
    """
    user_team_id = career.user_team_id
    tier_config = TIER_CONFIG.get(career.tier, TIER_CONFIG["ipl"])

    # 1. Determine user's final position and performance
    position = _get_team_position(db, season.id, user_team_id)
    is_champion = season.champion_team_id == user_team_id
    is_runner_up = season.runner_up_team_id == user_team_id
    team_count = tier_config["team_count"]

    # 2. Calculate reputation change
    rep_change = 0
    if is_champion:
        rep_change = REPUTATION_CHANGES["win_trophy"]
    elif is_runner_up:
        rep_change = REPUTATION_CHANGES["reach_final"]
    elif position and position <= 4:
        rep_change = REPUTATION_CHANGES["top_4"]
    elif position and position > team_count // 2:
        rep_change = REPUTATION_CHANGES["bottom_half"]

    if position == team_count:
        rep_change = REPUTATION_CHANGES["last_place"]

    new_rep = max(0, min(100, career.reputation + rep_change))
    career.reputation = new_rep

    # 3. Evaluate board objectives
    objectives = db.query(BoardObjective).filter_by(
        career_id=career.id, season_id=season.id
    ).all()

    objectives_met = []
    for obj in objectives:
        met = _check_objective(obj, position, is_champion, is_runner_up)
        obj.achieved = met
        if met:
            objectives_met.append(obj.description)

    # 4. Check promotion conditions
    promotion_available = False
    promotion_condition = tier_config.get("promotion_condition")
    if promotion_condition:
        current_idx = TIER_ORDER.index(career.tier) if career.tier in TIER_ORDER else 0
        if current_idx < len(TIER_ORDER) - 1:
            if promotion_condition == "win_trophy" and is_champion:
                promotion_available = True
            elif promotion_condition == "reach_final" and (is_champion or is_runner_up):
                promotion_available = True

    # 5. Check sacking conditions
    sacked = _check_sacking(db, career, season, position, tier_config)

    # 6. Update career state
    career.seasons_played += 1
    if is_champion:
        career.trophies_won += 1

    notifications = []

    if sacked:
        career.game_over = True
        career.game_over_reason = "sacked"
        career.status = CareerStatus.COMPLETED
        notifications.append(_create_notification(
            db, career.id, NotificationType.SACKED,
            "Board Loses Confidence",
            "The board has decided to part ways with you due to poor results. "
            "Your career as a manager has come to an end.",
            icon="alert-triangle",
        ))
        result = "sacked"
    elif promotion_available:
        career.status = CareerStatus.POST_SEASON
        next_tier = TIER_ORDER[TIER_ORDER.index(career.tier) + 1]
        notifications.append(_create_notification(
            db, career.id, NotificationType.PROMOTION,
            f"{next_tier.upper()} Cricket Awaits!",
            f"Congratulations! Your outstanding performance has caught the attention "
            f"of {next_tier.upper()} cricket. You have been invited to manage at the next level.",
            icon="trophy",
            action_url="/progression",
        ))
        result = "promotion_available"
    else:
        career.status = CareerStatus.POST_SEASON
        notifications.append(_create_notification(
            db, career.id, NotificationType.BOARD_OBJECTIVE,
            "Season Complete",
            f"Season {season.season_number} is over. "
            f"You finished in position {position}. "
            f"{'Well done!' if rep_change > 0 else 'The board expects improvement.'}",
            icon="bar-chart",
        ))
        result = "stay"

    # Match result notification
    if is_champion:
        notifications.append(_create_notification(
            db, career.id, NotificationType.MATCH_RESULT,
            "Champions!",
            f"You've won the {career.tier.upper()} Cup! What a season!",
            icon="trophy",
        ))
    elif is_runner_up:
        notifications.append(_create_notification(
            db, career.id, NotificationType.MATCH_RESULT,
            "Runner-Up",
            "So close! You reached the final but fell short. Better luck next time.",
            icon="medal",
        ))

    db.commit()

    return {
        "objectives_met": objectives_met,
        "reputation_change": rep_change,
        "new_reputation": new_rep,
        "promotion_available": promotion_available,
        "sacked": sacked,
        "result": result,
        "position": position,
        "is_champion": is_champion,
        "is_runner_up": is_runner_up,
        "notifications_created": len(notifications),
    }


def _get_team_position(db: Session, season_id: int, team_id: int) -> int:
    """Get the team's league position (1-indexed)."""
    all_stats = db.query(TeamSeasonStats).filter_by(season_id=season_id).all()
    if not all_stats:
        return None
    sorted_stats = sorted(all_stats, key=lambda s: (-s.points, -s.net_run_rate))
    for i, s in enumerate(sorted_stats):
        if s.team_id == team_id:
            return i + 1
    return None


def _check_objective(obj: BoardObjective, position: int, is_champion: bool, is_runner_up: bool) -> bool:
    """Check if a board objective has been met."""
    if obj.target_type == "win_trophy":
        return is_champion
    elif obj.target_type == "finish_position":
        return position is not None and position <= obj.target_value
    elif obj.target_type == "reach_final":
        return is_champion or is_runner_up
    elif obj.target_type == "win_count":
        # This would need actual win count from stats
        return False
    return False


def _check_sacking(db: Session, career: Career, current_season: Season,
                   position: int, tier_config: dict) -> bool:
    """Check if the sacking condition is met based on tier rules."""
    sack_condition = tier_config.get("sack_condition")
    if not sack_condition or not position:
        return False

    team_count = tier_config["team_count"]

    if sack_condition == "finish_last_twice":
        # Check if finished last in this + previous season
        if position != team_count:
            return False
        return _finished_last_in_previous_seasons(db, career, current_season, 1, team_count)

    elif sack_condition == "finish_bottom_half_twice":
        mid = team_count // 2
        if position <= mid:
            return False
        return _finished_bottom_half_in_previous(db, career, current_season, 1, team_count)

    elif sack_condition == "finish_last_three_times":
        if position != team_count:
            return False
        return _finished_last_in_previous_seasons(db, career, current_season, 2, team_count)

    return False


def _finished_last_in_previous_seasons(
    db: Session, career: Career, current_season: Season,
    num_previous: int, team_count: int
) -> bool:
    """Check if team finished last in the previous N seasons."""
    for offset in range(1, num_previous + 1):
        prev_season = db.query(Season).filter_by(
            career_id=career.id,
            season_number=current_season.season_number - offset,
        ).first()
        if not prev_season:
            return False
        prev_position = _get_team_position(db, prev_season.id, career.user_team_id)
        if prev_position != team_count:
            return False
    return True


def _finished_bottom_half_in_previous(
    db: Session, career: Career, current_season: Season,
    num_previous: int, team_count: int
) -> bool:
    """Check if team finished bottom half in the previous N seasons."""
    mid = team_count // 2
    for offset in range(1, num_previous + 1):
        prev_season = db.query(Season).filter_by(
            career_id=career.id,
            season_number=current_season.season_number - offset,
        ).first()
        if not prev_season:
            return False
        prev_position = _get_team_position(db, prev_season.id, career.user_team_id)
        if prev_position is None or prev_position <= mid:
            return False
    return True


def _create_notification(
    db: Session, career_id: int, ntype: NotificationType,
    title: str, body: str, icon: str = None, action_url: str = None
) -> Notification:
    """Create and add a notification to the session."""
    notif = Notification(
        career_id=career_id,
        type=ntype,
        title=title,
        body=body,
        icon=icon,
        action_url=action_url,
    )
    db.add(notif)
    return notif


def setup_next_season(db: Session, career: Career) -> Season:
    """
    Set up the next season at the same tier.
    Creates a new Season, generates fixtures, calendar, and objectives.
    """
    from app.models.team import Team
    from app.engine.season_engine import SeasonEngine
    from app.engine.calendar_engine import generate_season_calendar
    from app.models.playing_xi import PlayingXI
    from app.models.player import Player
    from app.api.career import _pick_best_xi

    tier_config = TIER_CONFIG.get(career.tier, TIER_CONFIG["ipl"])
    next_season_number = career.current_season_number + 1

    career.current_season_number = next_season_number
    career.status = CareerStatus.IN_SEASON

    # Create new season
    season = Season(
        career_id=career.id,
        season_number=next_season_number,
        phase=SeasonPhase.LEAGUE_STAGE,
        total_league_matches=tier_config["total_league_matches"],
    )
    db.add(season)
    db.flush()

    # Get teams
    teams = db.query(Team).filter_by(career_id=career.id).all()

    # Initialize season stats
    engine = SeasonEngine(db, season)
    engine.initialize_team_stats(teams)

    # Generate fixtures
    fixtures = engine.generate_league_fixtures(teams)

    # Auto-select XI for all teams
    for team in teams:
        players = db.query(Player).filter_by(team_id=team.id).all()
        xi = _pick_best_xi(players)
        for pos, player in enumerate(xi, 1):
            db.add(PlayingXI(
                team_id=team.id,
                season_id=season.id,
                player_id=player.id,
                position=pos,
            ))

    # Generate calendar
    generate_season_calendar(db, career, season, fixtures)

    # Create objectives based on tier
    _create_tier_objectives(db, career, season)

    db.commit()
    return season


def _create_tier_objectives(db: Session, career: Career, season: Season):
    """Create board objectives appropriate to the current tier."""
    tier = career.tier
    if tier == "district":
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Win the District Cup",
            target_type="win_trophy", target_value=1, consequence="promotion",
        ))
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Finish in Top 4",
            target_type="finish_position", target_value=4, consequence="stay",
        ))
    elif tier == "state":
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Reach the Final",
            target_type="reach_final", target_value=1, consequence="promotion",
        ))
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Finish in Top 4",
            target_type="finish_position", target_value=4, consequence="stay",
        ))
    elif tier == "ipl":
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Win the IPL Title",
            target_type="win_trophy", target_value=1, consequence="stay",
        ))
        db.add(BoardObjective(
            career_id=career.id, season_id=season.id,
            description="Qualify for Playoffs",
            target_type="finish_position", target_value=4, consequence="stay",
        ))
