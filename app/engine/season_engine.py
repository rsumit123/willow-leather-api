"""
Season Engine - Handles fixtures, league table, and playoffs
"""
import random
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.career import Season, Fixture, TeamSeasonStats, FixtureType, FixtureStatus, SeasonPhase
from app.models.match import Match, MatchStatus
from app.engine.match_engine import MatchEngine


@dataclass
class LeagueStanding:
    """Team standing in league table"""
    position: int
    team: Team
    played: int
    won: int
    lost: int
    no_result: int
    points: int
    nrr: float


@dataclass
class MatchResult:
    """Result of a simulated match"""
    fixture: Fixture
    winner: Optional[Team]
    margin: str
    innings1_score: str
    innings2_score: str
    player_of_match: Optional[str] = None


class SeasonEngine:
    """
    Manages season progression including fixtures, standings, and playoffs.
    """

    def __init__(self, session: Session, season: Season):
        self.session = session
        self.season = season
        self._match_engine = MatchEngine()

    def generate_league_fixtures(self, teams: list[Team]) -> list[Fixture]:
        """
        Generate round-robin fixtures where each team plays every other team twice.
        For 8 teams: 8 * 7 = 56 matches total (14 per team)
        """
        fixtures = []
        match_number = 1

        # Create all matchups
        matchups = []
        for i, team1 in enumerate(teams):
            for team2 in teams[i + 1:]:
                # Each pair plays twice (home and away)
                matchups.append((team1, team2))
                matchups.append((team2, team1))

        # Shuffle for variety
        random.shuffle(matchups)

        # Create fixtures with balanced scheduling
        # Try to ensure teams don't play too many consecutive matches
        scheduled = []
        team_last_match = {t.id: -3 for t in teams}  # Track when each team last played

        remaining_matchups = matchups.copy()

        while remaining_matchups:
            # Find a matchup where neither team played in the last 1-2 matches
            best_matchup = None
            best_score = -1

            for matchup in remaining_matchups:
                team1, team2 = matchup
                gap1 = match_number - team_last_match[team1.id]
                gap2 = match_number - team_last_match[team2.id]
                min_gap = min(gap1, gap2)

                if min_gap > best_score:
                    best_score = min_gap
                    best_matchup = matchup

            if best_matchup:
                team1, team2 = best_matchup
                remaining_matchups.remove(best_matchup)

                # Home team's ground
                venue = team1.home_ground

                fixture = Fixture(
                    season_id=self.season.id,
                    match_number=match_number,
                    fixture_type=FixtureType.LEAGUE,
                    team1_id=team1.id,
                    team2_id=team2.id,
                    venue=venue,
                    status=FixtureStatus.SCHEDULED,
                )
                fixtures.append(fixture)
                self.session.add(fixture)

                team_last_match[team1.id] = match_number
                team_last_match[team2.id] = match_number
                match_number += 1

        self.session.commit()
        return fixtures

    def initialize_team_stats(self, teams: list[Team]) -> list[TeamSeasonStats]:
        """Initialize season stats for all teams"""
        stats = []
        for team in teams:
            team_stats = TeamSeasonStats(
                season_id=self.season.id,
                team_id=team.id,
            )
            stats.append(team_stats)
            self.session.add(team_stats)
        self.session.commit()
        return stats

    def get_league_standings(self) -> list[LeagueStanding]:
        """Get current league standings sorted by points, then NRR"""
        stats = (
            self.session.query(TeamSeasonStats)
            .filter_by(season_id=self.season.id)
            .all()
        )

        # Sort by points (desc), then NRR (desc)
        sorted_stats = sorted(
            stats,
            key=lambda s: (s.points, s.net_run_rate),
            reverse=True
        )

        standings = []
        for pos, stat in enumerate(sorted_stats, 1):
            team = self.session.query(Team).get(stat.team_id)
            standings.append(LeagueStanding(
                position=pos,
                team=team,
                played=stat.matches_played,
                won=stat.wins,
                lost=stat.losses,
                no_result=stat.no_results,
                points=stat.points,
                nrr=stat.net_run_rate,
            ))

        return standings

    def get_next_fixture(self) -> Optional[Fixture]:
        """Get the next unplayed fixture"""
        return (
            self.session.query(Fixture)
            .filter_by(season_id=self.season.id, status=FixtureStatus.SCHEDULED)
            .order_by(Fixture.match_number)
            .first()
        )

    def simulate_match(self, fixture: Fixture) -> MatchResult:
        """
        Simulate a match and update all relevant stats.
        """
        team1 = self.session.query(Team).get(fixture.team1_id)
        team2 = self.session.query(Team).get(fixture.team2_id)

        # Get players for each team
        team1_players = [p for p in team1.players]
        team2_players = [p for p in team2.players]

        # Ensure we have enough players (use basic XI selection)
        team1_xi = self._select_playing_xi(team1_players)
        team2_xi = self._select_playing_xi(team2_players)

        if len(team1_xi) < 11 or len(team2_xi) < 11:
            # Not enough players - this shouldn't happen after auction
            raise ValueError(f"Not enough players for match: {team1.short_name} ({len(team1_xi)}) vs {team2.short_name} ({len(team2_xi)})")

        # Simulate toss
        toss_winner = random.choice([team1, team2])
        # Most teams prefer to chase in T20
        toss_decision = random.choices(["bowl", "bat"], weights=[70, 30])[0]

        if toss_decision == "bowl":
            batting_first = team2 if toss_winner == team1 else team1
        else:
            batting_first = toss_winner

        if batting_first == team1:
            first_xi = team1_xi
            second_xi = team2_xi
        else:
            first_xi = team2_xi
            second_xi = team1_xi

        # Simulate the match
        result = self._match_engine.simulate_match(first_xi, second_xi, team1_bats_first=(batting_first == team1))

        # Determine winner
        if result["winner"] == "team1":
            winner = team1 if batting_first == team1 else team2
        elif result["winner"] == "team2":
            winner = team2 if batting_first == team1 else team1
        else:
            winner = None  # Tie (rare)

        # Create match record
        match = Match(
            team1_id=team1.id,
            team2_id=team2.id,
            toss_winner_id=toss_winner.id,
            toss_decision=toss_decision,
            venue=fixture.venue,
            match_number=fixture.match_number,
            status=MatchStatus.COMPLETED,
            winner_id=winner.id if winner else None,
            result_summary=result["margin"],
        )
        self.session.add(match)

        # Update fixture
        fixture.status = FixtureStatus.COMPLETED
        fixture.match_id = match.id
        fixture.winner_id = winner.id if winner else None
        fixture.result_summary = result["margin"]

        # Update team season stats
        self._update_team_stats(team1, team2, winner, result, batting_first)

        # Update season progress
        self.season.current_match_number = fixture.match_number

        self.session.commit()

        # Format scores
        innings1 = result["innings1"]
        innings2 = result["innings2"]
        first_team = batting_first.short_name
        second_team = team2.short_name if batting_first == team1 else team1.short_name

        return MatchResult(
            fixture=fixture,
            winner=winner,
            margin=result["margin"],
            innings1_score=f"{first_team}: {innings1['runs']}/{innings1['wickets']} ({innings1['overs']})",
            innings2_score=f"{second_team}: {innings2['runs']}/{innings2['wickets']} ({innings2['overs']})",
        )

    def _select_playing_xi(self, players: list) -> list:
        """
        Select best XI from squad following rules:
        - Max 4 overseas players
        - At least 1 WK
        - Balance of batsmen, bowlers, all-rounders
        """
        from app.models.player import PlayerRole

        # Separate by role
        wks = [p for p in players if p.role == PlayerRole.WICKET_KEEPER]
        bats = [p for p in players if p.role == PlayerRole.BATSMAN]
        bowls = [p for p in players if p.role == PlayerRole.BOWLER]
        ars = [p for p in players if p.role == PlayerRole.ALL_ROUNDER]

        # Sort each by overall rating
        wks.sort(key=lambda p: p.overall_rating, reverse=True)
        bats.sort(key=lambda p: p.overall_rating, reverse=True)
        bowls.sort(key=lambda p: p.overall_rating, reverse=True)
        ars.sort(key=lambda p: p.overall_rating, reverse=True)

        xi = []
        overseas_count = 0

        def can_add(player):
            nonlocal overseas_count
            if player.is_overseas:
                if overseas_count >= 4:
                    return False
                overseas_count += 1
            return True

        # 1 WK (mandatory)
        for wk in wks:
            if can_add(wk):
                xi.append(wk)
                break

        # 4-5 batsmen
        for bat in bats[:5]:
            if len(xi) < 6 and can_add(bat):
                xi.append(bat)

        # 2-3 all-rounders
        for ar in ars[:3]:
            if len(xi) < 9 and can_add(ar):
                xi.append(ar)

        # 4-5 bowlers
        for bowl in bowls[:5]:
            if len(xi) < 11 and can_add(bowl):
                xi.append(bowl)

        # Fill remaining with best available
        all_remaining = [p for p in players if p not in xi]
        all_remaining.sort(key=lambda p: p.overall_rating, reverse=True)

        for player in all_remaining:
            if len(xi) >= 11:
                break
            if can_add(player):
                xi.append(player)

        return xi[:11]

    def _update_team_stats(self, team1: Team, team2: Team, winner: Optional[Team], result: dict, batting_first: Team):
        """Update team season statistics"""
        stats1 = self.session.query(TeamSeasonStats).filter_by(
            season_id=self.season.id, team_id=team1.id
        ).first()
        stats2 = self.session.query(TeamSeasonStats).filter_by(
            season_id=self.season.id, team_id=team2.id
        ).first()

        # Update matches played
        stats1.matches_played += 1
        stats2.matches_played += 1

        # Update wins/losses
        if winner == team1:
            stats1.wins += 1
            stats1.points += 2
            stats2.losses += 1
        elif winner == team2:
            stats2.wins += 1
            stats2.points += 2
            stats1.losses += 1
        else:
            # Tie or no result
            stats1.no_results += 1
            stats2.no_results += 1
            stats1.points += 1
            stats2.points += 1

        # Update NRR components
        innings1 = result["innings1"]
        innings2 = result["innings2"]

        # Parse overs to float (e.g., "19.4" -> 19.666...)
        def overs_to_float(overs_str: str) -> float:
            if '.' in overs_str:
                overs, balls = overs_str.split('.')
                return int(overs) + int(balls) / 6
            return float(overs_str)

        overs1 = overs_to_float(innings1["overs"])
        overs2 = overs_to_float(innings2["overs"])

        if batting_first == team1:
            # Team1 batted first
            stats1.runs_scored += innings1["runs"]
            stats1.overs_faced += overs1
            stats1.runs_conceded += innings2["runs"]
            stats1.overs_bowled += overs2

            stats2.runs_scored += innings2["runs"]
            stats2.overs_faced += overs2
            stats2.runs_conceded += innings1["runs"]
            stats2.overs_bowled += overs1
        else:
            # Team2 batted first
            stats2.runs_scored += innings1["runs"]
            stats2.overs_faced += overs1
            stats2.runs_conceded += innings2["runs"]
            stats2.overs_bowled += overs2

            stats1.runs_scored += innings2["runs"]
            stats1.overs_faced += overs2
            stats1.runs_conceded += innings1["runs"]
            stats1.overs_bowled += overs1

    def is_league_complete(self) -> bool:
        """Check if all league matches are played"""
        remaining = (
            self.session.query(Fixture)
            .filter_by(
                season_id=self.season.id,
                fixture_type=FixtureType.LEAGUE,
                status=FixtureStatus.SCHEDULED
            )
            .count()
        )
        return remaining == 0

    def generate_playoffs(self) -> list[Fixture]:
        """
        Generate playoff fixtures based on league standings.
        IPL format:
        - Qualifier 1: 1st vs 2nd
        - Eliminator: 3rd vs 4th
        - Qualifier 2: Loser of Q1 vs Winner of Eliminator
        - Final: Winner of Q1 vs Winner of Q2
        """
        standings = self.get_league_standings()
        top4 = standings[:4]

        # Get last match number
        last_match = (
            self.session.query(Fixture)
            .filter_by(season_id=self.season.id)
            .order_by(Fixture.match_number.desc())
            .first()
        )
        next_match_number = (last_match.match_number + 1) if last_match else 57

        fixtures = []

        # Qualifier 1: 1st vs 2nd
        q1 = Fixture(
            season_id=self.season.id,
            match_number=next_match_number,
            fixture_type=FixtureType.QUALIFIER_1,
            team1_id=top4[0].team.id,
            team2_id=top4[1].team.id,
            venue=top4[0].team.home_ground,  # Higher ranked team's home
            status=FixtureStatus.SCHEDULED,
        )
        fixtures.append(q1)
        self.session.add(q1)

        # Eliminator: 3rd vs 4th
        elim = Fixture(
            season_id=self.season.id,
            match_number=next_match_number + 1,
            fixture_type=FixtureType.ELIMINATOR,
            team1_id=top4[2].team.id,
            team2_id=top4[3].team.id,
            venue=top4[2].team.home_ground,
            status=FixtureStatus.SCHEDULED,
        )
        fixtures.append(elim)
        self.session.add(elim)

        # Q2 and Final will be created after Q1 and Eliminator are played
        self.session.commit()
        return fixtures

    def generate_qualifier2(self, q1_loser: Team, eliminator_winner: Team) -> Fixture:
        """Generate Qualifier 2 fixture"""
        last_match = (
            self.session.query(Fixture)
            .filter_by(season_id=self.season.id)
            .order_by(Fixture.match_number.desc())
            .first()
        )

        q2 = Fixture(
            season_id=self.season.id,
            match_number=last_match.match_number + 1,
            fixture_type=FixtureType.QUALIFIER_2,
            team1_id=q1_loser.id,
            team2_id=eliminator_winner.id,
            venue=q1_loser.home_ground,  # Q1 loser has home advantage
            status=FixtureStatus.SCHEDULED,
        )
        self.session.add(q2)
        self.session.commit()
        return q2

    def generate_final(self, q1_winner: Team, q2_winner: Team) -> Fixture:
        """Generate Final fixture"""
        last_match = (
            self.session.query(Fixture)
            .filter_by(season_id=self.season.id)
            .order_by(Fixture.match_number.desc())
            .first()
        )

        final = Fixture(
            season_id=self.season.id,
            match_number=last_match.match_number + 1,
            fixture_type=FixtureType.FINAL,
            team1_id=q1_winner.id,
            team2_id=q2_winner.id,
            venue="Narendra Modi Stadium",  # Neutral venue for final
            status=FixtureStatus.SCHEDULED,
        )
        self.session.add(final)
        self.session.commit()
        return final

    def complete_season(self, champion: Team, runner_up: Team) -> None:
        """Mark season as complete"""
        self.season.phase = SeasonPhase.COMPLETED
        self.season.champion_team_id = champion.id
        self.season.runner_up_team_id = runner_up.id
        self.session.commit()
