from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict
import random

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
    PlayerStateBrief, BowlerStateBrief, TossResultResponse, StartMatchRequest
)

# Store toss results for pending matches
pending_toss_results: Dict[int, dict] = {}

router = APIRouter(prefix="/match", tags=["Interactive Match"])

# In-memory store for active matches
# In production, this should be in Redis or DB
active_matches: Dict[int, MatchEngine] = {}

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
            is_nervous=s_state.is_nervous if s_state else False,
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
            is_nervous=ns_state.is_nervous if ns_state else False,
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
        is_collapse=innings.context.is_collapse_mode,
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
        innings_just_changed=innings_just_changed
    )

def _get_outcome_string(outcome: BallOutcome) -> str:
    if outcome.is_wicket: return "W"
    if outcome.is_wide: return "Wd"
    if outcome.is_no_ball: return "Nb"
    return str(outcome.runs)


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
        raise HTTPException(status_code=400, detail="Match already completed")

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

    # Start of over initialization
    if innings.balls == 0 and not innings.current_bowler_id:
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
        
        if b_state.is_nervous:
            b_state.nervous_balls_remaining -= 1
            if b_state.nervous_balls_remaining <= 0:
                b_state.is_nervous = False

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

    innings.total_runs += outcome.runs

    # Handle wicket
    if outcome.is_wicket:
        innings.wickets += 1
        batter_innings = innings.batter_innings[innings.striker_id]
        batter_innings.is_out = True
        batter_innings.dismissal = outcome.dismissal_type
        batter_innings.bowler = bowler
        spell.wickets += 1
        
        innings.context.recent_wickets.append((innings.overs * 6 + innings.balls, random.random()))
        # Check for collapse: 2 wickets in < 6 balls (stricter)
        recent = [w for w in innings.context.recent_wickets if (innings.overs * 6 + innings.balls) - w[0] < 6]
        innings.context.is_collapse_mode = len(recent) >= 2
        
        innings.bowler_states.setdefault(bowler.id, BowlerState(player_id=bowler.id)).has_confidence = True

        # Bring in next batter
        if innings.next_batter_index < len(innings.batting_order):
            next_batter_id = innings.batting_order[innings.next_batter_index]
            next_batter_obj = next(p for p in innings.batting_team if p.id == next_batter_id)
            innings.striker_id = next_batter_id
            innings.batter_innings[next_batter_id] = BatterInnings(player=next_batter_obj)
            # New batter state - nervous wears off after 3 balls
            innings.batter_states[next_batter_id] = BatterState(
                player_id=next_batter_id,
                is_nervous=innings.context.is_collapse_mode,
                nervous_balls_remaining=3 if innings.context.is_collapse_mode else 0
            )
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
            _finalize_match_interactive(engine, fixture, db)
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

def _finalize_match_interactive(engine: MatchEngine, fixture: Fixture, db: Session):
    # Determine winner
    target = engine.innings1.total_runs + 1
    winner = None
    if engine.innings2.total_runs >= target:
        winner = db.query(Team).get(engine.innings2.batting_team_id)
    elif engine.innings2.total_runs < target - 1:
        winner = db.query(Team).get(engine.innings1.batting_team_id)

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
        _finalize_match_interactive(engine, fixture, db)
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
        _finalize_match_interactive(engine, fixture, db)
        del active_matches[fixture_id]

    return _get_match_state_response(engine, fixture, db, innings_just_changed=innings_just_changed)
