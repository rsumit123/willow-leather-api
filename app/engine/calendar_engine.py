"""
Calendar Engine — Generates a day-by-day season calendar from fixtures.

Each season's fixtures are spread across the tier's calendar months.
Between user-team match days, training/rest/travel days are inserted.
"""
import calendar as cal
from datetime import date, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.career import Career, Season, Fixture, GameDay, DayType
from app.engine.tier_config import TIER_CONFIG

# Month name -> number
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Base year for in-game dates
BASE_YEAR = 2026


def generate_season_calendar(
    db: Session,
    career: Career,
    season: Season,
    fixtures: List[Fixture],
) -> List[GameDay]:
    """
    Generate a full calendar of GameDay entries for a season.

    Steps:
    1. Determine date range from tier's calendar_months
    2. Assign dates to fixtures (spread evenly, respecting rest gaps)
    3. For each day in the range, create a GameDay:
       - MATCH_DAY if a fixture involving the user's team is on this date
       - TRAINING if user's team has no match but there's a gap before next match
       - REST / TRAVEL for other days
    4. Mark the first day as is_current
    """
    tier = career.tier
    tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["ipl"])

    # 1. Get date range
    start_date, end_date = _get_season_date_range(tier_config, season.season_number)

    # 2. Assign dates to fixtures
    fixture_dates = _assign_fixture_dates(fixtures, start_date, end_date, tier_config)

    # 3. Build user-team match date set
    user_team_id = career.user_team_id
    user_match_dates = set()
    fixture_date_map = {}  # date_str -> fixture_id (for user's team)

    for fixture, d in fixture_dates:
        date_str = d.isoformat()
        if fixture.team1_id == user_team_id or fixture.team2_id == user_team_id:
            user_match_dates.add(d)
            fixture_date_map[date_str] = fixture.id

    # 4. Generate GameDay entries for every day in range
    game_days = []
    current = start_date
    day_index = 0

    while current <= end_date:
        date_str = current.isoformat()

        if current in user_match_dates:
            day_type = DayType.MATCH_DAY
            fixture_id = fixture_date_map.get(date_str)
            event_desc = None
        else:
            day_type, event_desc = _classify_non_match_day(
                current, user_match_dates, day_index, tier
            )
            fixture_id = None

        game_day = GameDay(
            career_id=career.id,
            season_id=season.id,
            date=date_str,
            day_type=day_type,
            fixture_id=fixture_id,
            event_description=event_desc,
            is_current=(day_index == 0),
        )
        db.add(game_day)
        game_days.append(game_day)

        current += timedelta(days=1)
        day_index += 1

    db.flush()
    return game_days


def _get_season_date_range(
    tier_config: dict, season_number: int
) -> Tuple[date, date]:
    """Calculate start and end dates for the season."""
    months = tier_config["calendar_months"]
    month_numbers = [MONTH_MAP[m] for m in months]

    # Offset year by season number (season 1 = BASE_YEAR, season 2 = BASE_YEAR+1, ...)
    year = BASE_YEAR + season_number - 1

    first_month = month_numbers[0]
    last_month = month_numbers[-1]

    start = date(year, first_month, 1)
    _, last_day = cal.monthrange(year, last_month)
    end = date(year, last_month, last_day)

    return start, end


def _assign_fixture_dates(
    fixtures: List[Fixture],
    start_date: date,
    end_date: date,
    tier_config: dict,
) -> List[Tuple[Fixture, date]]:
    """
    Spread fixtures evenly across the season date range.

    Returns list of (fixture, date) tuples.
    Each match day can have 1-2 fixtures (doubleheaders in dense schedules).
    """
    total_days = (end_date - start_date).days + 1
    total_fixtures = len(fixtures)

    if total_fixtures == 0:
        return []

    # Calculate spacing between match days
    # Leave first 2 days and last 2 days as buffer
    usable_days = total_days - 4
    start_offset = 2  # start matches from day 3

    if total_fixtures <= usable_days:
        # Can spread 1 match per day with gaps
        gap = usable_days / total_fixtures
        result = []
        for i, fixture in enumerate(fixtures):
            day_offset = start_offset + int(i * gap)
            match_date = start_date + timedelta(days=day_offset)
            if match_date > end_date:
                match_date = end_date
            result.append((fixture, match_date))
        return result
    else:
        # More fixtures than days — need doubleheaders
        # Pack 2 fixtures per day where needed
        result = []
        day_offset = start_offset
        for i, fixture in enumerate(fixtures):
            match_date = start_date + timedelta(days=day_offset)
            if match_date > end_date:
                match_date = end_date
            result.append((fixture, match_date))
            # Advance day every 2 fixtures (doubleheader)
            if i % 2 == 1:
                day_offset += 1
        return result


def _classify_non_match_day(
    current: date,
    user_match_dates: set,
    day_index: int,
    tier: str,
) -> Tuple[DayType, str]:
    """
    Classify a non-match day based on proximity to the user's matches.

    Pattern:
    - Day before a match: TRAVEL ("Travel to venue")
    - Day after a match: REST ("Recovery day")
    - 2 days before a match with no match yesterday: TRAINING
    - Otherwise: REST
    - First day of season: EVENT ("Season opener")
    """
    yesterday = current - timedelta(days=1)
    tomorrow = current + timedelta(days=1)
    day_after = current + timedelta(days=2)

    # First day of season
    if day_index == 0:
        return DayType.EVENT, "Season begins"

    # Day after a match -> rest
    if yesterday in user_match_dates:
        return DayType.REST, "Recovery day"

    # Day before a match -> travel
    if tomorrow in user_match_dates:
        return DayType.TRAVEL, "Travel to venue"

    # 2 days before a match -> training
    if day_after in user_match_dates:
        return DayType.TRAINING, "Training available"

    # Check if there's any match in the next 3-5 days (training opportunity)
    for offset in range(3, 6):
        future = current + timedelta(days=offset)
        if future in user_match_dates:
            return DayType.TRAINING, "Training available"

    # Default rest day
    return DayType.REST, None
