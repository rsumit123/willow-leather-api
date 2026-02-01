"""
Season API endpoints - fixtures, standings, matches, playoffs
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_session
from app.models.career import (
    Career, Season, Fixture, TeamSeasonStats, PlayerSeasonStats,
    CareerStatus, SeasonPhase, FixtureType, FixtureStatus
)
from app.models.team import Team
from app.models.player import PlayerRole
from app.models.user import User
from app.models.playing_xi import PlayingXI
from app.engine.season_engine import SeasonEngine
from app.validators.playing_xi_validator import PlayingXIValidator
from app.models.player import Player
from app.auth.utils import get_current_user
from app.api.schemas import (
    SeasonResponse, FixtureResponse, StandingResponse, MatchResultResponse,
    LeaderboardsResponse, BatterLeaderboardEntry, BowlerLeaderboardEntry,
    SixesLeaderboardEntry, CatchesLeaderboardEntry
)

router = APIRouter(prefix="/season", tags=["Season"])


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _auto_select_xi(team: Team) -> list:
    """Auto-select a valid playing XI for a team (AI logic)."""
    players = list(team.players)

    # Group by role
    wks = [p for p in players if p.role == PlayerRole.WICKET_KEEPER]
    batsmen = [p for p in players if p.role == PlayerRole.BATSMAN]
    all_rounders = [p for p in players if p.role == PlayerRole.ALL_ROUNDER]
    bowlers = [p for p in players if p.role == PlayerRole.BOWLER]

    # Sort each group by overall rating
    wks.sort(key=lambda p: p.overall_rating, reverse=True)
    batsmen.sort(key=lambda p: p.overall_rating, reverse=True)
    all_rounders.sort(key=lambda p: p.overall_rating, reverse=True)
    bowlers.sort(key=lambda p: p.overall_rating, reverse=True)

    xi = []
    overseas_count = 0

    def can_add(player):
        nonlocal overseas_count
        if player.is_overseas and overseas_count >= 4:
            return False
        return True

    def add_player(player):
        nonlocal overseas_count
        xi.append(player)
        if player.is_overseas:
            overseas_count += 1

    # Add 1 WK (mandatory)
    for wk in wks:
        if can_add(wk):
            add_player(wk)
            break

    # Add 5 bowlers (to meet minimum requirement)
    for bowler in bowlers:
        if len([p for p in xi if p.role == PlayerRole.BOWLER]) >= 5:
            break
        if can_add(bowler):
            add_player(bowler)

    # If we don't have 5 bowlers, add all-rounders to compensate
    bowler_count = len([p for p in xi if p.role == PlayerRole.BOWLER])
    if bowler_count < 5:
        needed_ar = max(1, 5 - bowler_count - 4)  # Need at least 1 AR if less than 5 bowlers
        for ar in all_rounders:
            if ar not in xi and can_add(ar):
                add_player(ar)
                if len([p for p in xi if p.role == PlayerRole.ALL_ROUNDER]) >= needed_ar:
                    break

    # Fill remaining with best available (batsmen first, then all-rounders)
    remaining_players = batsmen + [ar for ar in all_rounders if ar not in xi]
    remaining_players.sort(key=lambda p: p.overall_rating, reverse=True)

    for player in remaining_players:
        if len(xi) >= 11:
            break
        if player not in xi and can_add(player):
            add_player(player)

    # If still not at 11, add any remaining players regardless of overseas
    if len(xi) < 11:
        all_remaining = [p for p in players if p not in xi]
        all_remaining.sort(key=lambda p: p.overall_rating, reverse=True)
        for player in all_remaining:
            if len(xi) >= 11:
                break
            if player not in xi:
                add_player(player)

    return xi


def get_current_season(career_id: int, user_id: int, db: Session) -> tuple[Career, Season]:
    """Helper to get current season with ownership verification"""
    career = db.query(Career).filter_by(id=career_id, user_id=user_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    season = (
        db.query(Season)
        .filter_by(career_id=career_id, season_number=career.current_season_number)
        .first()
    )
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    return career, season


@router.get("/{career_id}", response_model=SeasonResponse)
def get_season_info(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current season info"""
    career, season = get_current_season(career_id, current_user.id, db)
    return SeasonResponse.model_validate(season)


@router.post("/{career_id}/generate-fixtures")
def generate_fixtures(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate league fixtures for the season"""
    career, season = get_current_season(career_id, current_user.id, db)

    if not season.auction_completed:
        raise HTTPException(status_code=400, detail="Complete auction first")

    # Check if fixtures already exist
    existing = db.query(Fixture).filter_by(season_id=season.id).count()
    if existing > 0:
        raise HTTPException(status_code=400, detail="Fixtures already generated")

    teams = db.query(Team).filter_by(career_id=career.id).all()
    if len(teams) != 8:
        raise HTTPException(status_code=400, detail=f"Need exactly 8 teams, found {len(teams)}")

    engine = SeasonEngine(db, season)

    # Initialize team stats
    engine.initialize_team_stats(teams)

    # Generate fixtures
    fixtures = engine.generate_league_fixtures(teams)

    # Auto-select and store XI for AI teams
    for team in teams:
        if not team.is_user_team:
            xi = _auto_select_xi(team)
            for pos, player in enumerate(xi, 1):
                db.add(PlayingXI(
                    team_id=team.id,
                    season_id=season.id,
                    player_id=player.id,
                    position=pos
                ))

    # Update career status
    career.status = CareerStatus.IN_SEASON
    season.phase = SeasonPhase.LEAGUE_STAGE
    db.commit()

    return {
        "message": "Fixtures generated",
        "total_matches": len(fixtures),
    }


@router.get("/{career_id}/fixtures", response_model=List[FixtureResponse])
def get_fixtures(
    career_id: int,
    fixture_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all fixtures for the season"""
    career, season = get_current_season(career_id, current_user.id, db)

    query = db.query(Fixture).filter_by(season_id=season.id)

    if fixture_type:
        query = query.filter_by(fixture_type=FixtureType(fixture_type))

    if status:
        query = query.filter_by(status=FixtureStatus(status))

    fixtures = query.order_by(Fixture.match_number).all()

    result = []
    for f in fixtures:
        team1 = db.query(Team).filter_by(id=f.team1_id).first()
        team2 = db.query(Team).filter_by(id=f.team2_id).first()
        result.append(FixtureResponse(
            id=f.id,
            match_number=f.match_number,
            fixture_type=f.fixture_type.value,
            team1_id=f.team1_id,
            team1_name=team1.short_name if team1 else "?",
            team2_id=f.team2_id,
            team2_name=team2.short_name if team2 else "?",
            venue=f.venue,
            status=f.status.value,
            winner_id=f.winner_id,
            result_summary=f.result_summary,
        ))

    return result


@router.get("/{career_id}/next-fixture", response_model=Optional[FixtureResponse])
def get_next_fixture(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the next scheduled fixture"""
    career, season = get_current_season(career_id, current_user.id, db)

    engine = SeasonEngine(db, season)
    fixture = engine.get_next_fixture()

    if not fixture:
        return None

    team1 = db.query(Team).filter_by(id=fixture.team1_id).first()
    team2 = db.query(Team).filter_by(id=fixture.team2_id).first()

    return FixtureResponse(
        id=fixture.id,
        match_number=fixture.match_number,
        fixture_type=fixture.fixture_type.value,
        team1_id=fixture.team1_id,
        team1_name=team1.short_name if team1 else "?",
        team2_id=fixture.team2_id,
        team2_name=team2.short_name if team2 else "?",
        venue=fixture.venue,
        status=fixture.status.value,
        winner_id=fixture.winner_id,
        result_summary=fixture.result_summary,
    )


@router.get("/{career_id}/standings", response_model=List[StandingResponse])
def get_standings(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current league standings"""
    career, season = get_current_season(career_id, current_user.id, db)

    engine = SeasonEngine(db, season)
    standings = engine.get_league_standings()

    return [
        StandingResponse(
            position=s.position,
            team_id=s.team.id,
            team_name=s.team.name,
            team_short_name=s.team.short_name,
            played=s.played,
            won=s.won,
            lost=s.lost,
            no_result=s.no_result,
            points=s.points,
            nrr=s.nrr,
        )
        for s in standings
    ]


@router.post("/{career_id}/simulate-match/{fixture_id}", response_model=MatchResultResponse)
def simulate_match(
    career_id: int,
    fixture_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Simulate a specific match"""
    career, season = get_current_season(career_id, current_user.id, db)

    fixture = db.query(Fixture).filter_by(id=fixture_id, season_id=season.id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if fixture.status != FixtureStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Match already played or in progress")

    engine = SeasonEngine(db, season)

    try:
        result = engine.simulate_match(fixture)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MatchResultResponse(
        fixture_id=fixture.id,
        winner_id=result.winner.id if result.winner else None,
        winner_name=result.winner.short_name if result.winner else None,
        margin=result.margin,
        innings1_score=result.innings1_score,
        innings2_score=result.innings2_score,
    )


@router.post("/{career_id}/simulate-next-match", response_model=MatchResultResponse)
def simulate_next_match(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Simulate the next scheduled match"""
    career, season = get_current_season(career_id, current_user.id, db)

    engine = SeasonEngine(db, season)
    fixture = engine.get_next_fixture()

    if not fixture:
        raise HTTPException(status_code=400, detail="No more matches to simulate")

    try:
        result = engine.simulate_match(fixture)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if league stage is complete
    if fixture.fixture_type == FixtureType.LEAGUE and engine.is_league_complete():
        season.phase = SeasonPhase.PLAYOFFS
        career.status = CareerStatus.PLAYOFFS
        # Generate playoff fixtures
        engine.generate_playoffs()
        db.commit()

    return MatchResultResponse(
        fixture_id=fixture.id,
        winner_id=result.winner.id if result.winner else None,
        winner_name=result.winner.short_name if result.winner else None,
        margin=result.margin,
        innings1_score=result.innings1_score,
        innings2_score=result.innings2_score,
    )


@router.post("/{career_id}/simulate-all-league")
def simulate_all_league_matches(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Simulate all remaining league matches"""
    career, season = get_current_season(career_id, current_user.id, db)

    engine = SeasonEngine(db, season)
    results = []

    while True:
        fixture = engine.get_next_fixture()
        if not fixture or fixture.fixture_type != FixtureType.LEAGUE:
            break

        try:
            result = engine.simulate_match(fixture)
            results.append({
                "match_number": fixture.match_number,
                "teams": f"{result.innings1_score.split(':')[0]} vs {result.innings2_score.split(':')[0]}",
                "winner": result.winner.short_name if result.winner else "Tie",
                "margin": result.margin,
            })
        except ValueError as e:
            results.append({
                "match_number": fixture.match_number,
                "error": str(e),
            })
            break

    # Update to playoffs
    if engine.is_league_complete():
        season.phase = SeasonPhase.PLAYOFFS
        career.status = CareerStatus.PLAYOFFS
        engine.generate_playoffs()
        db.commit()

    return {
        "matches_simulated": len(results),
        "results": results,
        "league_complete": engine.is_league_complete(),
    }


@router.post("/{career_id}/playoffs/generate-next")
def generate_next_playoff_fixture(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate the next playoff fixture based on results"""
    career, season = get_current_season(career_id, current_user.id, db)

    if season.phase != SeasonPhase.PLAYOFFS:
        raise HTTPException(status_code=400, detail="Not in playoffs phase")

    engine = SeasonEngine(db, season)

    # Check current state
    q1 = db.query(Fixture).filter_by(
        season_id=season.id, fixture_type=FixtureType.QUALIFIER_1
    ).first()
    elim = db.query(Fixture).filter_by(
        season_id=season.id, fixture_type=FixtureType.ELIMINATOR
    ).first()
    q2 = db.query(Fixture).filter_by(
        season_id=season.id, fixture_type=FixtureType.QUALIFIER_2
    ).first()
    final = db.query(Fixture).filter_by(
        season_id=season.id, fixture_type=FixtureType.FINAL
    ).first()

    # Need Q2?
    if (q1 and q1.status == FixtureStatus.COMPLETED and
        elim and elim.status == FixtureStatus.COMPLETED and
        not q2):
        # Get Q1 loser and Eliminator winner
        q1_loser_id = q1.team2_id if q1.winner_id == q1.team1_id else q1.team1_id
        q1_loser = db.query(Team).filter_by(id=q1_loser_id).first()
        elim_winner = db.query(Team).filter_by(id=elim.winner_id).first()

        if q1_loser and elim_winner:
            q2_fixture = engine.generate_qualifier2(q1_loser, elim_winner)
            return {"message": "Qualifier 2 generated", "fixture_id": q2_fixture.id}

    # Need Final?
    if (q1 and q1.status == FixtureStatus.COMPLETED and
        q2 and q2.status == FixtureStatus.COMPLETED and
        not final):
        q1_winner = db.query(Team).filter_by(id=q1.winner_id).first()
        q2_winner = db.query(Team).filter_by(id=q2.winner_id).first()

        if q1_winner and q2_winner:
            final_fixture = engine.generate_final(q1_winner, q2_winner)
            return {"message": "Final generated", "fixture_id": final_fixture.id}

    # Check if season complete
    if final and final.status == FixtureStatus.COMPLETED:
        champion = db.query(Team).filter_by(id=final.winner_id).first()
        runner_up_id = final.team2_id if final.winner_id == final.team1_id else final.team1_id
        runner_up = db.query(Team).filter_by(id=runner_up_id).first()

        engine.complete_season(champion, runner_up)
        career.status = CareerStatus.POST_SEASON
        db.commit()

        return {
            "message": "Season complete",
            "champion": champion.name,
            "runner_up": runner_up.name,
        }

    return {"message": "No new fixture needed yet"}


@router.get("/{career_id}/playoffs/bracket")
def get_playoff_bracket(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get playoff bracket status"""
    career, season = get_current_season(career_id, current_user.id, db)

    fixtures = db.query(Fixture).filter(
        Fixture.season_id == season.id,
        Fixture.fixture_type != FixtureType.LEAGUE
    ).all()

    bracket = {}
    for f in fixtures:
        team1 = db.query(Team).filter_by(id=f.team1_id).first()
        team2 = db.query(Team).filter_by(id=f.team2_id).first()
        winner = db.query(Team).filter_by(id=f.winner_id).first() if f.winner_id else None

        bracket[f.fixture_type.value] = {
            "fixture_id": f.id,
            "match_number": f.match_number,
            "team1": team1.short_name if team1 else None,
            "team1_id": f.team1_id,
            "team2": team2.short_name if team2 else None,
            "team2_id": f.team2_id,
            "winner": winner.short_name if winner else None,
            "status": f.status.value,
            "result": f.result_summary,
        }

    return bracket


@router.get("/{career_id}/leaderboards", response_model=LeaderboardsResponse)
def get_leaderboards(
    career_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament leaderboards (Orange Cap, Purple Cap, Most Sixes, Most Catches)"""
    career, season = get_current_season(career_id, current_user.id, db)

    # Get all player season stats for this season
    all_stats = (
        db.query(PlayerSeasonStats)
        .filter_by(season_id=season.id)
        .all()
    )

    # Build Orange Cap (top run scorers)
    batter_stats = sorted(
        [s for s in all_stats if s.runs > 0],
        key=lambda s: (-s.runs, -s.strike_rate)  # Primary: runs desc, Secondary: SR desc
    )[:10]

    # Helper to extract player details for modal
    def get_player_details(player):
        if not player:
            return {
                "role": "batsman",
                "is_overseas": False,
                "age": 25,
                "batting_style": "right_handed",
                "bowling_type": "medium",
                "batting": 50,
                "bowling": 50,
                "power": 50,
                "overall_rating": 50,
                "traits": [],
                "batting_intent": "accumulator",
            }
        import json
        traits = []
        if player.traits:
            try:
                traits = json.loads(player.traits) if isinstance(player.traits, str) else player.traits
            except (json.JSONDecodeError, TypeError):
                traits = []
        return {
            "role": player.role.value if hasattr(player.role, 'value') else str(player.role),
            "is_overseas": player.is_overseas,
            "age": player.age,
            "batting_style": player.batting_style.value if hasattr(player.batting_style, 'value') else str(player.batting_style),
            "bowling_type": player.bowling_type.value if hasattr(player.bowling_type, 'value') else str(player.bowling_type),
            "batting": player.batting,
            "bowling": player.bowling,
            "power": player.power,
            "overall_rating": player.overall_rating,
            "traits": traits,
            "batting_intent": player.batting_intent if player.batting_intent else "accumulator",
        }

    orange_cap = []
    for rank, stats in enumerate(batter_stats, 1):
        player = db.query(Player).get(stats.player_id)
        team = db.query(Team).get(stats.team_id)
        player_details = get_player_details(player)
        orange_cap.append(BatterLeaderboardEntry(
            rank=rank,
            player_id=stats.player_id,
            player_name=player.name if player else "Unknown",
            team_id=stats.team_id,
            team_short_name=team.short_name if team else "?",
            runs=stats.runs,
            matches=stats.matches_batted,
            innings=stats.matches_batted,
            not_outs=stats.not_outs,
            average=stats.batting_average,
            strike_rate=stats.strike_rate,
            fours=stats.fours,
            sixes=stats.sixes,
            highest_score=stats.highest_score,
            **player_details
        ))

    # Build Purple Cap (top wicket takers)
    bowler_stats = sorted(
        [s for s in all_stats if s.wickets > 0],
        key=lambda s: (-s.wickets, s.runs_conceded)  # Primary: wickets desc, Secondary: runs asc (tiebreaker)
    )[:10]

    purple_cap = []
    for rank, stats in enumerate(bowler_stats, 1):
        player = db.query(Player).get(stats.player_id)
        team = db.query(Team).get(stats.team_id)
        player_details = get_player_details(player)
        purple_cap.append(BowlerLeaderboardEntry(
            rank=rank,
            player_id=stats.player_id,
            player_name=player.name if player else "Unknown",
            team_id=stats.team_id,
            team_short_name=team.short_name if team else "?",
            wickets=stats.wickets,
            matches=stats.matches_bowled,
            overs=round(stats.overs_bowled, 1),
            runs_conceded=stats.runs_conceded,
            economy=stats.economy_rate,
            average=stats.bowling_average,
            best_bowling=stats.best_bowling,
            **player_details
        ))

    # Build Most Sixes
    sixes_stats = sorted(
        [s for s in all_stats if s.sixes > 0],
        key=lambda s: (-s.sixes, -s.runs)  # Primary: sixes desc, Secondary: runs desc
    )[:10]

    most_sixes = []
    for rank, stats in enumerate(sixes_stats, 1):
        player = db.query(Player).get(stats.player_id)
        team = db.query(Team).get(stats.team_id)
        player_details = get_player_details(player)
        most_sixes.append(SixesLeaderboardEntry(
            rank=rank,
            player_id=stats.player_id,
            player_name=player.name if player else "Unknown",
            team_id=stats.team_id,
            team_short_name=team.short_name if team else "?",
            sixes=stats.sixes,
            runs=stats.runs,
            matches=stats.matches_batted,
            **player_details
        ))

    # Build Most Catches/Dismissals
    fielding_stats = sorted(
        [s for s in all_stats if (s.catches + s.stumpings + s.run_outs) > 0],
        key=lambda s: (-(s.catches + s.stumpings + s.run_outs), -s.catches)
    )[:10]

    most_catches = []
    for rank, stats in enumerate(fielding_stats, 1):
        player = db.query(Player).get(stats.player_id)
        team = db.query(Team).get(stats.team_id)
        player_details = get_player_details(player)
        # Get matches - use max of batted/bowled as they may have only fielded
        matches = max(stats.matches_batted, stats.matches_bowled) if stats.matches_batted or stats.matches_bowled else 0
        most_catches.append(CatchesLeaderboardEntry(
            rank=rank,
            player_id=stats.player_id,
            player_name=player.name if player else "Unknown",
            team_id=stats.team_id,
            team_short_name=team.short_name if team else "?",
            catches=stats.catches,
            stumpings=stats.stumpings,
            run_outs=stats.run_outs,
            total_dismissals=stats.catches + stats.stumpings + stats.run_outs,
            matches=matches,
            **player_details
        ))

    return LeaderboardsResponse(
        orange_cap=orange_cap,
        purple_cap=purple_cap,
        most_sixes=most_sixes,
        most_catches=most_catches
    )
