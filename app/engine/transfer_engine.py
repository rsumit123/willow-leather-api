"""
Transfer Engine — Handles retention decisions, player releases, and next season setup.
IPL-style retention + mini-auction between seasons.
"""
import random
from typing import Optional
from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.player import Player, PlayerRole
from app.models.career import (
    Career, Season, PlayerSeasonStats, PlayerRetention,
    TeamSeasonStats, SeasonPhase, CareerStatus,
)
from app.models.auction import Auction, AuctionStatus
from app.generators.player_generator import PlayerGenerator


# IPL-style retention pricing (INR)
RETENTION_PRICES = {
    1: 180_000_000,  # 18 crore
    2: 140_000_000,  # 14 crore
    3: 110_000_000,  # 11 crore
    4:  80_000_000,  #  8 crore
}

SALARY_CAP = 900_000_000  # 90 crore
MAX_RETENTIONS = 4


def get_retention_candidates(session: Session, team: Team, season: Season):
    """
    Return the team's players sorted by retention value with slot pricing.
    """
    players = session.query(Player).filter_by(team_id=team.id).all()
    if not players:
        return []

    # Score each player for retention priority
    scored = []
    for p in players:
        stats = session.query(PlayerSeasonStats).filter_by(
            season_id=season.id, player_id=p.id
        ).first()

        score = _score_player(p, stats)
        scored.append((p, score, stats))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    candidates = []
    for i, (player, score, stats) in enumerate(scored):
        slot = i + 1
        if slot > MAX_RETENTIONS:
            break
        candidates.append({
            "player": player,
            "score": score,
            "retention_slot": slot,
            "retention_price": RETENTION_PRICES[slot],
            "season_stats": stats,
        })

    return candidates


def _score_player(player: Player, stats: Optional[PlayerSeasonStats]) -> float:
    """
    Score a player for retention priority (0-1 scale).
    - Overall rating (40%)
    - Season performance (30%)
    - Current form (15%)
    - Age factor — younger preferred (15%)
    """
    # Rating component (0-1)
    rating_score = min(player.overall_rating / 100.0, 1.0)

    # Season performance (0-1)
    perf_score = 0.0
    if stats:
        # Batting contribution
        bat_score = 0.0
        if stats.runs > 0:
            bat_score = min(stats.runs / 500.0, 1.0) * 0.5  # 500 runs = max
            sr_bonus = min(stats.strike_rate / 200.0, 1.0) * 0.2 if stats.balls_faced > 0 else 0
            bat_score += sr_bonus

        # Bowling contribution
        bowl_score = 0.0
        if stats.wickets > 0:
            bowl_score = min(stats.wickets / 20.0, 1.0) * 0.5  # 20 wickets = max
            econ_bonus = max(0, (10.0 - stats.economy_rate) / 10.0) * 0.2 if stats.overs_bowled > 0 else 0
            bowl_score += econ_bonus

        role = player.role.value if hasattr(player.role, 'value') else str(player.role)
        if role in ('batsman', 'wicket_keeper'):
            perf_score = bat_score * 0.8 + bowl_score * 0.2
        elif role == 'bowler':
            perf_score = bowl_score * 0.8 + bat_score * 0.2
        else:  # all_rounder
            perf_score = bat_score * 0.5 + bowl_score * 0.5

    # Form component (0-1)
    form = getattr(player, 'form', 1.0) or 1.0
    form_score = (form - 0.7) / 0.6  # Maps 0.7-1.3 to 0-1

    # Age factor (younger = higher, peak at 26)
    age = getattr(player, 'age', 28) or 28
    if age <= 26:
        age_score = 0.9 + (26 - age) * 0.02  # Younger gets slight bonus
    elif age <= 30:
        age_score = 0.9 - (age - 26) * 0.05
    else:
        age_score = max(0.2, 0.7 - (age - 30) * 0.1)

    return (
        rating_score * 0.40
        + perf_score * 0.30
        + form_score * 0.15
        + min(age_score, 1.0) * 0.15
    )


def process_user_retentions(
    session: Session,
    season: Season,
    team: Team,
    player_ids: list[int],
) -> list[PlayerRetention]:
    """
    Process the user's retention choices. Returns list of PlayerRetention records.
    """
    if len(player_ids) > MAX_RETENTIONS:
        raise ValueError(f"Cannot retain more than {MAX_RETENTIONS} players")

    # Verify all players belong to the team
    players = session.query(Player).filter(
        Player.id.in_(player_ids),
        Player.team_id == team.id,
    ).all()

    if len(players) != len(player_ids):
        raise ValueError("Some players do not belong to your team")

    retentions = []
    for slot, player in enumerate(players, start=1):
        retention = PlayerRetention(
            season_id=season.id,
            team_id=team.id,
            player_id=player.id,
            retention_slot=slot,
            retention_price=RETENTION_PRICES[slot],
        )
        session.add(retention)
        retentions.append(retention)

    session.flush()
    return retentions


def process_ai_retentions(
    session: Session,
    season: Season,
    teams: list[Team],
    user_team_id: int,
) -> list[dict]:
    """
    AI teams decide their retentions. Returns summary for each team.
    """
    results = []

    for team in teams:
        if team.id == user_team_id:
            continue

        candidates = get_retention_candidates(session, team, season)
        if not candidates:
            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "retained_players": [],
                "total_cost": 0,
            })
            continue

        # AI retains top 2-4 players if score is high enough
        # Higher-rated teams retain more aggressively
        avg_rating = sum(c["player"].overall_rating for c in candidates) / len(candidates) if candidates else 60
        threshold = 0.30 if avg_rating >= 70 else 0.35

        retained = []
        total_cost = 0

        for candidate in candidates:
            if candidate["score"] < threshold:
                break
            if total_cost + candidate["retention_price"] > SALARY_CAP * 0.6:
                break  # Don't spend more than 60% on retentions

            retention = PlayerRetention(
                season_id=season.id,
                team_id=team.id,
                player_id=candidate["player"].id,
                retention_slot=candidate["retention_slot"],
                retention_price=candidate["retention_price"],
            )
            session.add(retention)
            total_cost += candidate["retention_price"]
            retained.append({
                "player_id": candidate["player"].id,
                "player_name": candidate["player"].name,
                "retention_slot": candidate["retention_slot"],
                "retention_price": candidate["retention_price"],
            })

        results.append({
            "team_id": team.id,
            "team_name": team.name,
            "retained_players": retained,
            "total_cost": total_cost,
        })

    session.flush()
    return results


def release_and_generate_pool(
    session: Session,
    season: Season,
    career: Career,
    teams: list[Team],
) -> int:
    """
    Release all non-retained players and generate new players for the auction pool.
    Returns the total number of available players for mini-auction.
    """
    # Get all retentions for this season
    retentions = session.query(PlayerRetention).filter_by(season_id=season.id).all()
    retained_player_ids = {r.player_id for r in retentions}

    # Release all non-retained players from all teams
    released_count = 0
    for team in teams:
        players = session.query(Player).filter_by(team_id=team.id).all()
        for player in players:
            if player.id not in retained_player_ids:
                player.team_id = None
                player.sold_price = None
                released_count += 1

    # Generate 15-20 new players for the pool
    new_count = random.randint(15, 20)
    new_players = []

    # Distribution: 2 star, 5 good, rest solid
    for _ in range(2):
        p = PlayerGenerator.generate_player(tier="star")
        session.add(p)
        new_players.append(p)

    for _ in range(5):
        p = PlayerGenerator.generate_player(tier="good")
        session.add(p)
        new_players.append(p)

    for _ in range(new_count - 7):
        p = PlayerGenerator.generate_player(tier="solid")
        session.add(p)
        new_players.append(p)

    session.flush()

    # Count total available players (released + new, no team)
    total_pool = session.query(Player).filter(Player.team_id.is_(None)).count()
    return total_pool


def prepare_next_season(
    session: Session,
    career: Career,
    teams: list[Team],
) -> Season:
    """
    Create the next season, reset team budgets based on retention costs,
    create fresh TeamSeasonStats, and transition career to AUCTION for mini-auction.
    """
    current_season = session.query(Season).filter_by(
        career_id=career.id,
        season_number=career.current_season_number,
    ).first()

    # Create new season
    next_number = career.current_season_number + 1
    new_season = Season(
        career_id=career.id,
        season_number=next_number,
        phase=SeasonPhase.AUCTION,
        auction_completed=False,
    )
    session.add(new_season)
    session.flush()

    # Reset team budgets (salary cap minus retention costs)
    for team in teams:
        retentions = session.query(PlayerRetention).filter_by(
            season_id=current_season.id,
            team_id=team.id,
        ).all()
        retention_cost = sum(r.retention_price for r in retentions)
        team.budget = SALARY_CAP
        team.remaining_budget = SALARY_CAP - retention_cost

        # Create TeamSeasonStats for the new season
        tss = TeamSeasonStats(
            season_id=new_season.id,
            team_id=team.id,
        )
        session.add(tss)

    # Update career
    career.current_season_number = next_number
    career.status = CareerStatus.AUCTION

    # Update old season phase
    current_season.phase = SeasonPhase.COMPLETED

    session.flush()
    return new_season


def create_mini_auction(
    session: Session,
    new_season: Season,
    teams: list[Team],
) -> Auction:
    """
    Create an Auction record for the mini-auction using the released + new player pool.
    Reuses the standard AuctionEngine infrastructure.
    """
    # Get all unassigned players as the auction pool
    pool = session.query(Player).filter(Player.team_id.is_(None)).all()

    auction = Auction(
        season_id=new_season.id,
        status=AuctionStatus.NOT_STARTED,
        salary_cap=SALARY_CAP,
        min_squad_size=18,
        max_squad_size=25,
        max_overseas=8,
        total_players=len(pool),
    )
    session.add(auction)
    session.flush()

    return auction
