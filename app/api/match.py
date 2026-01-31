from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
import random
import json

from app.database import get_session
from app.models.career import Career, Fixture, FixtureStatus, FixtureType, Season, SeasonPhase, CareerStatus
from app.models.team import Team
from app.models.player import Player, PlayerRole
from app.models.match import Match, MatchStatus
from app.models.playing_xi import PlayingXI
from app.engine.match_engine import (
    MatchEngine, InningsState, BallOutcome,
    BatterState, BowlerState, BatterInnings, BowlerSpell
)
from app.engine.season_engine import SeasonEngine
from app.api.schemas import (
    MatchStateResponse, BallRequest, BallResultResponse,
    PlayerStateBrief, BowlerStateBrief, TossResultResponse, StartMatchRequest,
    AvailableBowlerResponse, AvailableBowlersResponse, SelectBowlerRequest,
    BatterScorecardEntry, BowlerScorecardEntry, ExtrasBreakdown,
    InningsScorecard, ManOfTheMatch, LiveScorecardResponse, MatchCompletionResponse
)

# Store toss results for pending matches
pending_toss_results: Dict[int, dict] = {}

router = APIRouter(prefix="/match", tags=["Interactive Match"])

# In-memory store for active matches
# In production, this should be in Redis or DB
active_matches: Dict[int, MatchEngine] = {}

# Store completed match results temporarily so they can be fetched after match ends
# Key: fixture_id, Value: dict with engine copy and winner info
completed_match_results: Dict[int, dict] = {}


def _parse_traits(traits_json: Optional[str]) -> List[str]:
    """Parse traits JSON string to list of trait strings"""
    if not traits_json:
        return []
    try:
        return json.loads(traits_json)
    except (json.JSONDecodeError, TypeError):
        return []


def _store_completed_match(fixture_id: int, engine: MatchEngine, winner_id: Optional[int], margin: str):
    """Store completed match data so it can be fetched after removal from active_matches"""
    completed_match_results[fixture_id] = {
        "engine": engine,
        "winner_id": winner_id,
        "margin": margin
    }

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _get_playing_xi(team: Team, season_id: int, db: Session) -> list:
    """Get playing XI for a team. Uses stored XI if exists, falls back to top 11 by rating."""
    xi_entries = db.query(PlayingXI).filter_by(
        team_id=team.id,
        season_id=season_id
    ).order_by(PlayingXI.position).all()

    if xi_entries and len(xi_entries) == 11:
        # Use stored XI
        return [entry.player for entry in xi_entries]

    # Fallback: top 11 by overall rating
    return sorted(team.players, key=lambda p: p.overall_rating, reverse=True)[:11]


def _refresh_engine_players(engine: MatchEngine, db: Session):
    """Re-bind player objects to the current database session to avoid DetachedInstanceError"""
    if not engine.innings1:
        return

    # Helper to refresh a player and update all references to it
    def get_refreshed_player(p):
        return db.merge(p)

    for innings in [engine.innings1, engine.innings2]:
        if not innings:
            continue
        
        # Refresh teams
        innings.batting_team = [get_refreshed_player(p) for p in innings.batting_team]
        innings.bowling_team = [get_refreshed_player(p) for p in innings.bowling_team]

        # Refresh players in batter_innings
        for bi in innings.batter_innings.values():
            bi.player = get_refreshed_player(bi.player)
            if bi.bowler:
                bi.bowler = get_refreshed_player(bi.bowler)
            if bi.fielder:
                bi.fielder = get_refreshed_player(bi.fielder)
        
        # Refresh players in bowler_spells
        for bs in innings.bowler_spells.values():
            bs.player = get_refreshed_player(bs.player)

def _get_match_state_response(engine: MatchEngine, fixture: Fixture, db: Session, user_team_id: Optional[int] = None, innings_just_changed: bool = False) -> MatchStateResponse:
    _refresh_engine_players(engine, db)
    innings = engine.current_innings
    if not innings:
        raise HTTPException(status_code=400, detail="Match not initialized")

    # Determine team names for clarity
    batting_team_id = innings.batting_team_id
    batting_team = db.query(Team).get(batting_team_id) if batting_team_id else None
    bowling_team_id = fixture.team2_id if batting_team_id == fixture.team1_id else fixture.team1_id
    bowling_team = db.query(Team).get(bowling_team_id)

    # Get user team info
    if user_team_id is None and hasattr(engine, 'user_team_id'):
        user_team_id = engine.user_team_id
    user_team = db.query(Team).get(user_team_id) if user_team_id else None
    is_user_batting = batting_team_id == user_team_id if user_team_id else False
    
    striker = next((p for p in innings.batting_team if p.id == innings.striker_id), None)
    non_striker = next((p for p in innings.batting_team if p.id == innings.non_striker_id), None)
    bowler = next((p for p in innings.bowling_team if p.id == innings.current_bowler_id), None)
    
    s_brief = None
    if striker:
        s_inn = innings.batter_innings.get(striker.id)
        s_state = innings.batter_states.get(striker.id)
        s_brief = PlayerStateBrief(
            id=striker.id,
            name=striker.name,
            runs=s_inn.runs if s_inn else 0,
            balls=s_inn.balls if s_inn else 0,
            fours=s_inn.fours if s_inn else 0,
            sixes=s_inn.sixes if s_inn else 0,
            is_out=s_inn.is_out if s_inn else False,
            is_settled=s_state.is_settled if s_state else False,
            is_on_fire=s_state.is_on_fire if s_state else False
        )

    ns_brief = None
    if non_striker:
        ns_inn = innings.batter_innings.get(non_striker.id)
        ns_state = innings.batter_states.get(non_striker.id)
        ns_brief = PlayerStateBrief(
            id=non_striker.id,
            name=non_striker.name,
            runs=ns_inn.runs if ns_inn else 0,
            balls=ns_inn.balls if ns_inn else 0,
            fours=ns_inn.fours if ns_inn else 0,
            sixes=ns_inn.sixes if ns_inn else 0,
            is_out=ns_inn.is_out if ns_inn else False,
            is_settled=ns_state.is_settled if ns_state else False,
            is_on_fire=ns_state.is_on_fire if ns_state else False
        )
        
    b_brief = None
    if bowler:
        b_spell = innings.bowler_spells.get(bowler.id)
        b_state = innings.bowler_states.get(bowler.id)
        b_brief = BowlerStateBrief(
            id=bowler.id,
            name=bowler.name,
            overs=b_spell.overs if b_spell else 0,
            balls=b_spell.balls if b_spell else 0,
            runs=b_spell.runs if b_spell else 0,
            wickets=b_spell.wickets if b_spell else 0,
            is_tired=b_state.is_tired if b_state else False,
            has_confidence=b_state.has_confidence if b_state else False
        )

    last_ball = innings.this_over[-1] if innings.this_over else None
    
    # Determine phase
    if innings.overs < 6:
        phase = "Powerplay"
    elif innings.overs < 15:
        phase = "Middle Overs"
    else:
        phase = "Death Overs"

    status = "in_progress"
    winner_name = None
    margin = None
    
    if engine.innings2 and engine.innings2.is_innings_complete:
        status = "completed"
        # Determine winner
        target = engine.innings1.total_runs + 1
        if engine.innings2.total_runs >= target:
            winner = fixture.team2 if engine.innings2.batting_team_id == fixture.team2_id else fixture.team1
            winner_name = winner.short_name
            margin = f"{10 - engine.innings2.wickets} wickets"
        elif engine.innings2.total_runs < target - 1:
            winner = fixture.team1 if engine.innings2.batting_team_id == fixture.team2_id else fixture.team2
            winner_name = winner.short_name
            margin = f"{(target - 1) - engine.innings2.total_runs} runs"
        else:
            winner_name = "Tie"
            margin = "Match tied!"

    # User can change bowler at the start of an over when they are fielding
    is_user_bowling = not is_user_batting
    can_change_bowler = innings.balls == 0 and is_user_bowling and status == "in_progress"

    return MatchStateResponse(
        innings=1 if engine.current_innings == engine.innings1 else 2,
        runs=innings.total_runs,
        wickets=innings.wickets,
        overs=innings.overs_display,
        run_rate=round(innings.run_rate, 2),
        required_rate=round(innings.required_rate, 2) if innings.required_rate else None,
        target=innings.target,
        striker=s_brief,
        non_striker=ns_brief,
        bowler=b_brief,
        pitch_type=innings.context.pitch_type,
        is_pressure=innings.context.is_pressure_cooker,
        partnership_runs=innings.context.partnership_runs,
        this_over=[_get_outcome_string(b) for b in innings.this_over],
        last_ball_commentary=last_ball.commentary if last_ball else None,
        phase=phase,
        balls_remaining=(20 * 6) - (innings.overs * 6 + innings.balls),
        status=status,
        winner_name=winner_name,
        margin=margin,
        batting_team_name=batting_team.short_name if batting_team else "",
        bowling_team_name=bowling_team.short_name if bowling_team else "",
        is_user_batting=is_user_batting,
        user_team_name=user_team.short_name if user_team else "",
        innings_just_changed=innings_just_changed,
        can_change_bowler=can_change_bowler
    )

def _get_outcome_string(outcome: BallOutcome) -> str:
    if outcome.is_wicket: return "W"
    if outcome.is_wide: return "Wd"
    if outcome.is_no_ball: return "Nb"
    return str(outcome.runs)


def _format_dismissal(batter_innings: BatterInnings) -> str:
    """Convert dismissal info to readable string"""
    if not batter_innings.is_out:
        return "not out"

    dismissal = batter_innings.dismissal
    bowler = batter_innings.bowler
    fielder = batter_innings.fielder

    bowler_name = bowler.name if bowler else "Unknown"

    if dismissal == "bowled":
        return f"b {bowler_name}"
    elif dismissal == "lbw":
        return f"lbw b {bowler_name}"
    elif dismissal == "caught":
        if fielder:
            return f"c {fielder.name} b {bowler_name}"
        return f"c & b {bowler_name}"
    elif dismissal == "caught_behind":
        return f"c †wk b {bowler_name}"
    elif dismissal == "run_out":
        if fielder:
            return f"run out ({fielder.name})"
        return "run out"
    elif dismissal == "stumped":
        return f"st †wk b {bowler_name}"
    else:
        return f"b {bowler_name}"


def _build_innings_scorecard(innings: InningsState, batting_team: Team, bowling_team: Team) -> InningsScorecard:
    """Convert InningsState to response schema"""
    # Build batter entries - sorted by batting order position
    batters = []
    batted_ids = set()

    for position, player_id in enumerate(innings.batting_order):
        if player_id in innings.batter_innings:
            bi = innings.batter_innings[player_id]
            batted_ids.add(player_id)
            batters.append(BatterScorecardEntry(
                player_id=player_id,
                player_name=bi.player.name,
                runs=bi.runs,
                balls=bi.balls,
                fours=bi.fours,
                sixes=bi.sixes,
                strike_rate=round(bi.strike_rate, 2),
                is_out=bi.is_out,
                dismissal=_format_dismissal(bi),
                batting_position=position + 1,
                traits=_parse_traits(bi.player.traits)
            ))

    # Calculate extras from bowler spells
    total_wides = 0
    total_no_balls = 0
    for spell in innings.bowler_spells.values():
        total_wides += spell.wides
        total_no_balls += spell.no_balls

    extras = ExtrasBreakdown(
        wides=total_wides,
        no_balls=total_no_balls,
        total=total_wides + total_no_balls
    )

    # Build bowler entries - sorted by overs bowled (most first)
    bowlers = []
    for player_id, spell in sorted(
        innings.bowler_spells.items(),
        key=lambda x: (x[1].overs * 6 + x[1].balls),
        reverse=True
    ):
        bowlers.append(BowlerScorecardEntry(
            player_id=player_id,
            player_name=spell.player.name,
            overs=spell.overs_display,
            runs=spell.runs,
            wickets=spell.wickets,
            economy=round(spell.economy, 2),
            wides=spell.wides,
            no_balls=spell.no_balls
        ))

    # Did not bat list
    did_not_bat = []
    for player_id in innings.batting_order:
        if player_id not in batted_ids:
            player = next((p for p in innings.batting_team if p.id == player_id), None)
            if player:
                did_not_bat.append(player.name)

    return InningsScorecard(
        batting_team_name=batting_team.short_name,
        bowling_team_name=bowling_team.short_name,
        total_runs=innings.total_runs,
        wickets=innings.wickets,
        overs=innings.overs_display,
        run_rate=round(innings.run_rate, 2),
        extras=extras,
        batters=batters,
        bowlers=bowlers,
        did_not_bat=did_not_bat
    )


def _calculate_man_of_the_match(engine: MatchEngine, winner_id: int, db: Session) -> ManOfTheMatch:
    """Calculate man of the match from winning team"""
    # Collect all performances from winning team across both innings
    player_impacts = {}  # player_id -> {batting_impact, bowling_impact, name, team_name, bat_summary, bowl_summary}

    winner_team = db.query(Team).get(winner_id)

    # Process both innings
    for innings in [engine.innings1, engine.innings2]:
        if not innings:
            continue

        is_winner_batting = innings.batting_team_id == winner_id

        if is_winner_batting:
            # Count batting contributions from winning team
            for player_id, bi in innings.batter_innings.items():
                if player_id not in player_impacts:
                    player_impacts[player_id] = {
                        'batting_impact': 0,
                        'bowling_impact': 0,
                        'name': bi.player.name,
                        'team_name': winner_team.short_name,
                        'bat_runs': 0,
                        'bat_balls': 0,
                        'bowl_wickets': 0,
                        'bowl_runs': 0
                    }

                # Batting Impact = runs × (1 + (strike_rate - 100) / 200)
                sr = bi.strike_rate if bi.balls > 0 else 100
                batting_impact = bi.runs * (1 + (sr - 100) / 200)
                player_impacts[player_id]['batting_impact'] += batting_impact
                player_impacts[player_id]['bat_runs'] += bi.runs
                player_impacts[player_id]['bat_balls'] += bi.balls
        else:
            # Count bowling contributions from winning team (they are bowling)
            for player_id, spell in innings.bowler_spells.items():
                if player_id not in player_impacts:
                    player = spell.player
                    player_impacts[player_id] = {
                        'batting_impact': 0,
                        'bowling_impact': 0,
                        'name': player.name,
                        'team_name': winner_team.short_name,
                        'bat_runs': 0,
                        'bat_balls': 0,
                        'bowl_wickets': 0,
                        'bowl_runs': 0
                    }

                # Bowling Impact = wickets × 25 × (1 + (6.0 - economy) / 6)
                economy = spell.economy if (spell.overs * 6 + spell.balls) > 0 else 6.0
                bowling_impact = spell.wickets * 25 * (1 + (6.0 - economy) / 6)
                player_impacts[player_id]['bowling_impact'] += bowling_impact
                player_impacts[player_id]['bowl_wickets'] += spell.wickets
                player_impacts[player_id]['bowl_runs'] += spell.runs

    # Find player with highest total impact
    best_player_id = None
    best_impact = -1

    for player_id, data in player_impacts.items():
        total_impact = data['batting_impact'] + data['bowling_impact']
        if total_impact > best_impact:
            best_impact = total_impact
            best_player_id = player_id

    if best_player_id is None:
        # Fallback - shouldn't happen
        return ManOfTheMatch(
            player_id=0,
            player_name="Unknown",
            team_name=winner_team.short_name,
            performance_summary="N/A",
            impact_score=0
        )

    data = player_impacts[best_player_id]

    # Build performance summary
    parts = []
    if data['bat_runs'] > 0 or data['bat_balls'] > 0:
        parts.append(f"{data['bat_runs']}({data['bat_balls']})")
    if data['bowl_wickets'] > 0:
        parts.append(f"{data['bowl_wickets']}/{data['bowl_runs']}")

    performance_summary = " & ".join(parts) if parts else "N/A"

    return ManOfTheMatch(
        player_id=best_player_id,
        player_name=data['name'],
        team_name=data['team_name'],
        performance_summary=performance_summary,
        impact_score=round(best_impact, 1)
    )


@router.post("/{career_id}/match/{fixture_id}/toss")
def do_toss(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    """Perform toss and return result"""
    fixture = db.query(Fixture).filter_by(id=fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if fixture.status == FixtureStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Match already completed")

    career = db.query(Career).get(career_id)
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    user_team = db.query(Team).get(career.user_team_id)

    toss_winner_id = random.choice([fixture.team1_id, fixture.team2_id])
    toss_winner = db.query(Team).get(toss_winner_id)
    user_won_toss = toss_winner_id == user_team.id

    # Store toss result for later use in start_match
    pending_toss_results[fixture_id] = {
        "toss_winner_id": toss_winner_id,
        "user_team_id": user_team.id
    }

    return TossResultResponse(
        toss_winner_id=toss_winner_id,
        toss_winner_name=toss_winner.short_name,
        user_won_toss=user_won_toss,
        user_team_name=user_team.short_name
    )


@router.post("/{career_id}/match/{fixture_id}/start")
def start_match(
    career_id: int,
    fixture_id: int,
    request: Optional[StartMatchRequest] = None,
    db: Session = Depends(get_db)
):
    """Start match with toss decision. If no request body, uses auto toss."""
    fixture = db.query(Fixture).filter_by(id=fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if fixture.status == FixtureStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Match already completed. Result: {fixture.result_summary or 'Unknown'}")

    # If match was in progress but server restarted (lost active state), allow restart
    if fixture.status == FixtureStatus.IN_PROGRESS and fixture_id not in active_matches:
        # Reset to scheduled so we can start fresh
        fixture.status = FixtureStatus.SCHEDULED
        db.commit()

    career = db.query(Career).get(career_id)
    if not career:
        raise HTTPException(status_code=404, detail="Career not found")

    # Get teams and players
    team1 = db.query(Team).get(fixture.team1_id)
    team2 = db.query(Team).get(fixture.team2_id)

    # Get season for XI lookup
    season = db.query(Season).get(fixture.season_id)

    # Get playing XI (stored or fallback to top 11 by rating)
    team1_players = _get_playing_xi(team1, season.id, db)
    team2_players = _get_playing_xi(team2, season.id, db)

    engine = MatchEngine()

    # Determine batting order based on toss
    if request:
        # User provided toss decision
        toss_winner_id = request.toss_winner_id
        elected_to = request.elected_to
        toss_winner = db.query(Team).get(toss_winner_id)

        if elected_to == "bat":
            batting_first = toss_winner
        else:
            batting_first = team2 if toss_winner == team1 else team1
    else:
        # Auto toss (for backwards compatibility)
        toss_winner = random.choice([team1, team2])
        elected_to = "bowl"  # AI always bowls
        batting_first = team2 if toss_winner == team1 else team1

    team1_bats_first = batting_first == team1

    engine.innings1 = engine.setup_innings(
        team1_players if team1_bats_first else team2_players,
        team2_players if team1_bats_first else team1_players
    )
    # Add batting_team_id for winner determination
    engine.innings1.batting_team_id = batting_first.id

    # Store user team id for is_user_batting calculation
    engine.user_team_id = career.user_team_id

    # Initialize pitch
    engine.innings1.context.pitch_type = random.choice(["green_top", "dust_bowl", "flat_deck"])

    engine.current_innings = engine.innings1

    # Select first bowler
    bowler = engine.select_bowler(engine.innings1)
    engine.innings1.current_bowler_id = bowler.id

    active_matches[fixture_id] = engine

    # Clean up pending toss result if exists
    if fixture_id in pending_toss_results:
        del pending_toss_results[fixture_id]

    # Update fixture status
    fixture.status = FixtureStatus.IN_PROGRESS
    db.commit()

    return _get_match_state_response(engine, fixture, db, career.user_team_id)

@router.get("/{career_id}/match/{fixture_id}/state")
def get_match_state(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")
    
    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    fixture = db.query(Fixture).get(fixture_id)
    return _get_match_state_response(engine, fixture, db)

@router.post("/{career_id}/match/{fixture_id}/ball")
def play_ball(career_id: int, fixture_id: int, request: BallRequest, db: Session = Depends(get_db)):
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")
    
    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    innings = engine.current_innings
    fixture = db.query(Fixture).get(fixture_id)
    
    innings_just_changed = False
    if innings.is_innings_complete:
        # Check if we need to start 2nd innings
        if innings == engine.innings1:
            # Start 2nd innings
            target = engine.innings1.total_runs + 1
            # Second team bats
            team1_bats_first = engine.innings1.batting_team_id == fixture.team1_id
            season = db.query(Season).get(fixture.season_id)
            batting_team = fixture.team2 if team1_bats_first else fixture.team1
            bowling_team = fixture.team1 if team1_bats_first else fixture.team2
            batting_team_players = _get_playing_xi(batting_team, season.id, db)
            bowling_team_players = _get_playing_xi(bowling_team, season.id, db)

            engine.innings2 = engine.setup_innings(batting_team_players, bowling_team_players, target=target)
            engine.innings2.batting_team_id = fixture.team2_id if team1_bats_first else fixture.team1_id
            engine.innings2.context.pitch_type = engine.innings1.context.pitch_type # Same pitch
            engine.current_innings = engine.innings2

            # Select first bowler for 2nd innings
            bowler = engine.select_bowler(engine.innings2)
            engine.innings2.current_bowler_id = bowler.id
            innings = engine.innings2
            innings_just_changed = True
        else:
            raise HTTPException(status_code=400, detail="Match already complete")

    # Start of over initialization - auto-select bowler only if AI is bowling
    if innings.balls == 0 and not innings.current_bowler_id:
        # Check if user is bowling (user should select manually)
        user_team_id = getattr(engine, 'user_team_id', None)
        batting_team_id = innings.batting_team_id
        is_user_batting = batting_team_id == user_team_id if user_team_id else False
        is_user_bowling = not is_user_batting

        if is_user_bowling:
            # User must select bowler manually
            raise HTTPException(status_code=400, detail="Please select a bowler first")
        else:
            # AI bowling - auto-select
            bowler_obj = engine.select_bowler(innings)
            innings.current_bowler_id = bowler_obj.id
            innings.this_over = []

    # Get striker and bowler
    striker = next(p for p in innings.batting_team if p.id == innings.striker_id)
    bowler = next(p for p in innings.bowling_team if p.id == innings.current_bowler_id)
    
    fielders = [p for p in innings.bowling_team if p.id != bowler.id]

    # Simulate ball
    outcome = engine._simulate_ball(striker, bowler, innings, fielders, aggression=request.aggression)
    innings.this_over.append(outcome)
    
    # Update states (similar to simulate_over but for one ball)
    if not outcome.is_wide and not outcome.is_no_ball:
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
        b_state = innings.batter_states.setdefault(striker.id, BatterState(player_id=striker.id))
        b_state.balls_faced += 1
        b_state.is_settled = b_state.balls_faced > 15
        if outcome.is_boundary:
            b_state.recent_outcomes.append("4/6")
        else:
            b_state.recent_outcomes.append("other")
        
        # On fire check: 2 boundaries in last 3 balls
        if len(b_state.recent_outcomes) >= 3:
            recent_3 = b_state.recent_outcomes[-3:]
            b_state.is_on_fire = recent_3.count("4/6") >= 2

    # Update bowler spell
    if bowler.id not in innings.bowler_spells:
        innings.bowler_spells[bowler.id] = BowlerSpell(player=bowler)
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
        spell.balls += 1  # Track balls bowled (legal deliveries only)

    innings.total_runs += outcome.runs

    # Handle wicket
    if outcome.is_wicket:
        innings.wickets += 1
        batter_innings = innings.batter_innings[innings.striker_id]
        batter_innings.is_out = True
        batter_innings.dismissal = outcome.dismissal_type
        batter_innings.bowler = bowler
        spell.wickets += 1

        innings.bowler_states.setdefault(bowler.id, BowlerState(player_id=bowler.id)).has_confidence = True

        # Bring in next batter
        if innings.next_batter_index < len(innings.batting_order):
            next_batter_id = innings.batting_order[innings.next_batter_index]
            next_batter_obj = next(p for p in innings.batting_team if p.id == next_batter_id)
            innings.striker_id = next_batter_id
            innings.batter_innings[next_batter_id] = BatterInnings(player=next_batter_obj)
            innings.batter_states[next_batter_id] = BatterState(player_id=next_batter_id)
            innings.next_batter_index += 1
    elif outcome.runs % 2 == 1:
        innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id

    # Over end
    if innings.balls >= 6:
        innings.overs += 1
        innings.balls = 0
        spell.overs += 1
        spell.balls = 0
        innings.last_bowler_id = bowler.id
        
        b_state = innings.bowler_states.setdefault(bowler.id, BowlerState(player_id=bowler.id))
        b_state.consecutive_overs += 1
        b_state.is_tired = b_state.consecutive_overs > 4
        
        # Reset current bowler so next over needs selection
        innings.current_bowler_id = None
        
        # Rotate strike at end of over
        innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id

    # Check if innings complete
    if innings.is_innings_complete:
        if innings == engine.innings2:
            # Match complete! Save to DB
            winner_id, margin = _finalize_match_interactive(engine, fixture, db)
            _store_completed_match(fixture_id, engine, winner_id, margin)
            del active_matches[fixture_id]

    return BallResultResponse(
        outcome=_get_outcome_string(outcome),
        runs=outcome.runs,
        is_wicket=outcome.is_wicket,
        is_boundary=outcome.is_boundary,
        is_six=outcome.is_six,
        commentary=outcome.commentary,
        match_state=_get_match_state_response(engine, fixture, db, innings_just_changed=innings_just_changed)
    )

def _finalize_match_interactive(engine: MatchEngine, fixture: Fixture, db: Session) -> tuple:
    """Finalize match and return (winner_id, margin) tuple"""
    # Determine winner
    target = engine.innings1.total_runs + 1
    winner = None
    margin = ""
    if engine.innings2.total_runs >= target:
        winner = db.query(Team).get(engine.innings2.batting_team_id)
        margin = f"{10 - engine.innings2.wickets} wickets"
    elif engine.innings2.total_runs < target - 1:
        winner = db.query(Team).get(engine.innings1.batting_team_id)
        margin = f"{(target - 1) - engine.innings2.total_runs} runs"
    else:
        margin = "Match tied!"

    # Create match record
    match = Match(
        team1_id=fixture.team1_id,
        team2_id=fixture.team2_id,
        venue=fixture.venue,
        match_number=fixture.match_number,
        status=MatchStatus.COMPLETED,
        winner_id=winner.id if winner else None,
        result_summary="Match completed via simulation"
    )
    db.add(match)

    fixture.status = FixtureStatus.COMPLETED
    fixture.match_id = match.id
    fixture.winner_id = winner.id if winner else None
    fixture.result_summary = f"{winner.short_name if winner else 'Tie'}"

    # Update standings using SeasonEngine logic
    season = db.query(Season).get(fixture.season_id)
    engine_season = SeasonEngine(db, season)

    # Result dict for _update_team_stats
    result_dict = {
        "innings1": {"runs": engine.innings1.total_runs, "overs": engine.innings1.overs_display, "wickets": engine.innings1.wickets},
        "innings2": {"runs": engine.innings2.total_runs, "overs": engine.innings2.overs_display, "wickets": engine.innings2.wickets},
        "winner": "team1" if (winner and winner.id == fixture.team1_id) else "team2" if (winner and winner.id == fixture.team2_id) else "tie"
    }
    batting_first = db.query(Team).get(engine.innings1.batting_team_id)
    engine_season._update_team_stats(fixture.team1, fixture.team2, winner, result_dict, batting_first)

    # Check if league stage is complete - transition to playoffs
    career = db.query(Career).filter_by(id=season.career_id).first()
    if fixture.fixture_type == FixtureType.LEAGUE and engine_season.is_league_complete():
        season.phase = SeasonPhase.PLAYOFFS
        career.status = CareerStatus.PLAYOFFS
        engine_season.generate_playoffs()

    # Handle playoff match completion - check if we need to generate next playoff or complete season
    if fixture.fixture_type in [FixtureType.QUALIFIER_1, FixtureType.ELIMINATOR, FixtureType.QUALIFIER_2, FixtureType.FINAL]:
        # Get all playoff fixtures to check state
        q1 = db.query(Fixture).filter_by(season_id=season.id, fixture_type=FixtureType.QUALIFIER_1).first()
        elim = db.query(Fixture).filter_by(season_id=season.id, fixture_type=FixtureType.ELIMINATOR).first()
        q2 = db.query(Fixture).filter_by(season_id=season.id, fixture_type=FixtureType.QUALIFIER_2).first()
        final = db.query(Fixture).filter_by(season_id=season.id, fixture_type=FixtureType.FINAL).first()

        # Generate Q2 if needed
        if (q1 and q1.status == FixtureStatus.COMPLETED and
            elim and elim.status == FixtureStatus.COMPLETED and
            not q2):
            q1_loser_id = q1.team2_id if q1.winner_id == q1.team1_id else q1.team1_id
            q1_loser = db.query(Team).filter_by(id=q1_loser_id).first()
            elim_winner = db.query(Team).filter_by(id=elim.winner_id).first()
            if q1_loser and elim_winner:
                engine_season.generate_qualifier2(q1_loser, elim_winner)

        # Generate Final if needed
        elif (q1 and q1.status == FixtureStatus.COMPLETED and
              q2 and q2.status == FixtureStatus.COMPLETED and
              not final):
            q1_winner = db.query(Team).filter_by(id=q1.winner_id).first()
            q2_winner = db.query(Team).filter_by(id=q2.winner_id).first()
            if q1_winner and q2_winner:
                engine_season.generate_final(q1_winner, q2_winner)

        # Complete season if Final is done
        elif final and final.status == FixtureStatus.COMPLETED:
            champion = db.query(Team).filter_by(id=final.winner_id).first()
            runner_up_id = final.team2_id if final.winner_id == final.team1_id else final.team1_id
            runner_up = db.query(Team).filter_by(id=runner_up_id).first()
            engine_season.complete_season(champion, runner_up)
            career.status = CareerStatus.POST_SEASON

    db.commit()
    return (winner.id if winner else None, margin)

@router.post("/{career_id}/match/{fixture_id}/simulate-over")
def simulate_over_interactive(career_id: int, fixture_id: int, request: Optional[BallRequest] = None, db: Session = Depends(get_db)):
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")

    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    innings = engine.current_innings
    fixture = db.query(Fixture).get(fixture_id)

    was_innings1 = innings == engine.innings1

    # Simulate rest of the over with user's aggression choice
    aggression = request.aggression if request else "balanced"
    engine.simulate_over(innings, aggression)

    innings_just_changed = False

    # Check if innings 1 just completed and we need to start innings 2
    if innings.is_innings_complete and was_innings1:
        # Start 2nd innings
        target = engine.innings1.total_runs + 1
        team1_bats_first = engine.innings1.batting_team_id == fixture.team1_id
        season = db.query(Season).get(fixture.season_id)
        batting_team = fixture.team2 if team1_bats_first else fixture.team1
        bowling_team = fixture.team1 if team1_bats_first else fixture.team2
        batting_team_players = _get_playing_xi(batting_team, season.id, db)
        bowling_team_players = _get_playing_xi(bowling_team, season.id, db)

        engine.innings2 = engine.setup_innings(batting_team_players, bowling_team_players, target=target)
        engine.innings2.batting_team_id = fixture.team2_id if team1_bats_first else fixture.team1_id
        engine.innings2.context.pitch_type = engine.innings1.context.pitch_type
        engine.current_innings = engine.innings2

        # Select first bowler for 2nd innings
        bowler = engine.select_bowler(engine.innings2)
        engine.innings2.current_bowler_id = bowler.id
        innings_just_changed = True
    elif innings.is_innings_complete and innings == engine.innings2:
        winner_id, margin = _finalize_match_interactive(engine, fixture, db)
        _store_completed_match(fixture_id, engine, winner_id, margin)
        del active_matches[fixture_id]

    return _get_match_state_response(engine, fixture, db, innings_just_changed=innings_just_changed)

@router.post("/{career_id}/match/{fixture_id}/simulate-innings")
def simulate_innings_interactive(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")

    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    innings = engine.current_innings
    fixture = db.query(Fixture).get(fixture_id)

    was_innings1 = innings == engine.innings1

    # Simulate rest of the innings
    engine.simulate_innings(innings)

    innings_just_changed = False

    # Check if innings 1 just completed and we need to start innings 2
    if innings.is_innings_complete and was_innings1:
        # Start 2nd innings
        target = engine.innings1.total_runs + 1
        team1_bats_first = engine.innings1.batting_team_id == fixture.team1_id
        season = db.query(Season).get(fixture.season_id)
        batting_team = fixture.team2 if team1_bats_first else fixture.team1
        bowling_team = fixture.team1 if team1_bats_first else fixture.team2
        batting_team_players = _get_playing_xi(batting_team, season.id, db)
        bowling_team_players = _get_playing_xi(bowling_team, season.id, db)

        engine.innings2 = engine.setup_innings(batting_team_players, bowling_team_players, target=target)
        engine.innings2.batting_team_id = fixture.team2_id if team1_bats_first else fixture.team1_id
        engine.innings2.context.pitch_type = engine.innings1.context.pitch_type
        engine.current_innings = engine.innings2

        # Select first bowler for 2nd innings
        bowler = engine.select_bowler(engine.innings2)
        engine.innings2.current_bowler_id = bowler.id
        innings_just_changed = True
    elif innings.is_innings_complete and innings == engine.innings2:
        winner_id, margin = _finalize_match_interactive(engine, fixture, db)
        _store_completed_match(fixture_id, engine, winner_id, margin)
        del active_matches[fixture_id]

    return _get_match_state_response(engine, fixture, db, innings_just_changed=innings_just_changed)


@router.get("/{career_id}/match/{fixture_id}/available-bowlers")
def get_available_bowlers(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    """Get bowlers available for next over"""
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")

    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    innings = engine.current_innings

    if not innings:
        raise HTTPException(status_code=400, detail="Match not initialized")

    # Get all players, sorted by bowling skill (best bowlers first)
    bowlers = sorted(innings.bowling_team, key=lambda p: p.bowling, reverse=True)

    available_bowlers = []
    for b in bowlers:
        spell = innings.bowler_spells.get(b.id)
        overs_int = spell.overs if spell else 0
        balls_int = spell.balls if spell else 0
        overs_display = spell.overs_display if spell else "0.0"
        wickets = spell.wickets if spell else 0
        runs_conceded = spell.runs if spell else 0
        economy = spell.economy if spell else 0.0

        can_bowl = True
        reason = None

        # Check if bowled max overs (4 complete overs)
        if overs_int >= 4:
            can_bowl = False
            reason = "Bowled maximum 4 overs"
        # Check if was last bowler
        elif b.id == innings.last_bowler_id:
            can_bowl = False
            reason = "Bowled last over"

        available_bowlers.append(AvailableBowlerResponse(
            id=b.id,
            name=b.name,
            bowling_type=b.bowling_type.value,
            bowling_skill=b.bowling,
            overs_bowled=overs_display,
            wickets=wickets,
            runs_conceded=runs_conceded,
            economy=round(economy, 2),
            can_bowl=can_bowl,
            reason=reason
        ))

    return AvailableBowlersResponse(
        bowlers=available_bowlers,
        last_bowler_id=innings.last_bowler_id
    )


@router.post("/{career_id}/match/{fixture_id}/select-bowler")
def select_bowler_manual(career_id: int, fixture_id: int, request: SelectBowlerRequest, db: Session = Depends(get_db)):
    """Manually select bowler for next over"""
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")

    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    innings = engine.current_innings
    fixture = db.query(Fixture).get(fixture_id)

    if not innings:
        raise HTTPException(status_code=400, detail="Match not initialized")

    # Can only change bowler at start of over
    if innings.balls != 0:
        raise HTTPException(status_code=400, detail="Can only change bowler at start of over")

    # Validate bowler exists in bowling team
    bowler = next((p for p in innings.bowling_team if p.id == request.bowler_id), None)
    if not bowler:
        raise HTTPException(status_code=400, detail="Invalid bowler selection")

    spell = innings.bowler_spells.get(bowler.id)
    if spell and spell.overs >= 4:
        raise HTTPException(status_code=400, detail="Bowler has already bowled maximum 4 overs")

    if bowler.id == innings.last_bowler_id:
        raise HTTPException(status_code=400, detail="Cannot bowl consecutive overs")

    # Set the selected bowler
    innings.current_bowler_id = bowler.id

    # Initialize bowler spell if needed
    if bowler.id not in innings.bowler_spells:
        innings.bowler_spells[bowler.id] = BowlerSpell(player=bowler)

    # Initialize bowler state if needed
    if bowler.id not in innings.bowler_states:
        innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)

    return _get_match_state_response(engine, fixture, db)


@router.get("/{career_id}/match/{fixture_id}/scorecard")
def get_live_scorecard(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    """Get live scorecard during an active match"""
    if fixture_id not in active_matches:
        raise HTTPException(status_code=404, detail="Active match session not found")

    engine = active_matches[fixture_id]
    _refresh_engine_players(engine, db)
    fixture = db.query(Fixture).get(fixture_id)

    innings1_scorecard = None
    innings2_scorecard = None
    current_innings = 1

    if engine.innings1:
        # Get batting team for innings 1
        batting_team_id = engine.innings1.batting_team_id
        batting_team = db.query(Team).get(batting_team_id)
        bowling_team_id = fixture.team2_id if batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team = db.query(Team).get(bowling_team_id)
        innings1_scorecard = _build_innings_scorecard(engine.innings1, batting_team, bowling_team)

    if engine.innings2:
        # Get batting team for innings 2
        batting_team_id = engine.innings2.batting_team_id
        batting_team = db.query(Team).get(batting_team_id)
        bowling_team_id = fixture.team2_id if batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team = db.query(Team).get(bowling_team_id)
        innings2_scorecard = _build_innings_scorecard(engine.innings2, batting_team, bowling_team)
        current_innings = 2

    return LiveScorecardResponse(
        innings1=innings1_scorecard,
        innings2=innings2_scorecard,
        current_innings=current_innings
    )


@router.get("/{career_id}/match/{fixture_id}/result")
def get_match_result(career_id: int, fixture_id: int, db: Session = Depends(get_db)):
    """Get complete match result with scorecard and Man of the Match after match ends"""
    # First check if match is still active (just completed)
    if fixture_id in active_matches:
        engine = active_matches[fixture_id]
        _refresh_engine_players(engine, db)

        # Verify match is complete
        if not engine.innings2 or not engine.innings2.is_innings_complete:
            raise HTTPException(status_code=400, detail="Match not yet complete")

        fixture = db.query(Fixture).get(fixture_id)

        # Determine winner
        target = engine.innings1.total_runs + 1
        if engine.innings2.total_runs >= target:
            winner_id = engine.innings2.batting_team_id
            winner = db.query(Team).get(winner_id)
            margin = f"{10 - engine.innings2.wickets} wickets"
        elif engine.innings2.total_runs < target - 1:
            winner_id = engine.innings1.batting_team_id
            winner = db.query(Team).get(winner_id)
            margin = f"{(target - 1) - engine.innings2.total_runs} runs"
        else:
            # Tie
            winner_id = engine.innings1.batting_team_id  # Arbitrary for MoM
            winner = db.query(Team).get(winner_id)
            margin = "Match tied!"

        # Build scorecards for both innings
        batting_team_1 = db.query(Team).get(engine.innings1.batting_team_id)
        bowling_team_1_id = fixture.team2_id if engine.innings1.batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team_1 = db.query(Team).get(bowling_team_1_id)
        innings1_scorecard = _build_innings_scorecard(engine.innings1, batting_team_1, bowling_team_1)

        batting_team_2 = db.query(Team).get(engine.innings2.batting_team_id)
        bowling_team_2_id = fixture.team2_id if engine.innings2.batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team_2 = db.query(Team).get(bowling_team_2_id)
        innings2_scorecard = _build_innings_scorecard(engine.innings2, batting_team_2, bowling_team_2)

        # Calculate Man of the Match
        mom = _calculate_man_of_the_match(engine, winner_id, db)

        return MatchCompletionResponse(
            winner_name=winner.short_name,
            margin=margin,
            innings1=innings1_scorecard,
            innings2=innings2_scorecard,
            man_of_the_match=mom
        )

    # Check if match was recently completed and stored
    if fixture_id in completed_match_results:
        stored = completed_match_results[fixture_id]
        engine = stored["engine"]
        winner_id = stored["winner_id"]
        margin = stored["margin"]

        # Re-bind player objects to the current database session
        _refresh_engine_players(engine, db)

        fixture = db.query(Fixture).get(fixture_id)
        winner = db.query(Team).get(winner_id) if winner_id else None

        # Build scorecards for both innings
        batting_team_1 = db.query(Team).get(engine.innings1.batting_team_id)
        bowling_team_1_id = fixture.team2_id if engine.innings1.batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team_1 = db.query(Team).get(bowling_team_1_id)
        innings1_scorecard = _build_innings_scorecard(engine.innings1, batting_team_1, bowling_team_1)

        batting_team_2 = db.query(Team).get(engine.innings2.batting_team_id)
        bowling_team_2_id = fixture.team2_id if engine.innings2.batting_team_id == fixture.team1_id else fixture.team1_id
        bowling_team_2 = db.query(Team).get(bowling_team_2_id)
        innings2_scorecard = _build_innings_scorecard(engine.innings2, batting_team_2, bowling_team_2)

        # Calculate Man of the Match
        mom = _calculate_man_of_the_match(engine, winner_id if winner_id else engine.innings1.batting_team_id, db)

        # Clean up stored result after fetching
        del completed_match_results[fixture_id]

        return MatchCompletionResponse(
            winner_name=winner.short_name if winner else "Tie",
            margin=margin,
            innings1=innings1_scorecard,
            innings2=innings2_scorecard,
            man_of_the_match=mom
        )

    # Match not in memory - check if it was completed and saved
    fixture = db.query(Fixture).get(fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if fixture.status != FixtureStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Match not found or not complete")

    # For completed matches that are no longer in memory, we don't have detailed stats
    # This is a limitation - in production you'd want to persist the full scorecard
    raise HTTPException(
        status_code=404,
        detail="Match scorecard no longer available. Detailed scorecards are only available immediately after match completion."
    )