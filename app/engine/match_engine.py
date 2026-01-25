import random
from dataclasses import dataclass, field
from typing import Optional
from app.models.player import Player, PlayerRole, BowlingType


@dataclass
class BatterInnings:
    """Tracks a batter's innings"""
    player: Player
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    is_out: bool = False
    dismissal: str = ""
    bowler: Optional[Player] = None
    fielder: Optional[Player] = None

    @property
    def strike_rate(self) -> float:
        if self.balls == 0:
            return 0.0
        return (self.runs / self.balls) * 100


@dataclass
class BowlerSpell:
    """Tracks a bowler's spell"""
    player: Player
    overs: int = 0
    balls: int = 0
    runs: int = 0
    wickets: int = 0
    wides: int = 0
    no_balls: int = 0

    @property
    def overs_display(self) -> str:
        return f"{self.overs}.{self.balls}"

    @property
    def economy(self) -> float:
        total_balls = self.overs * 6 + self.balls
        if total_balls == 0:
            return 0.0
        return (self.runs / total_balls) * 6


@dataclass
class BallOutcome:
    """Result of a single ball"""
    runs: int = 0
    is_wicket: bool = False
    is_wide: bool = False
    is_no_ball: bool = False
    is_bye: bool = False
    is_leg_bye: bool = False
    is_boundary: bool = False
    is_six: bool = False
    dismissal_type: str = ""
    commentary: str = ""


@dataclass
class InningsState:
    """Current state of an innings"""
    batting_team: list[Player]
    bowling_team: list[Player]
    total_runs: int = 0
    wickets: int = 0
    overs: int = 0
    balls: int = 0
    target: Optional[int] = None

    batter_innings: dict = field(default_factory=dict)  # player_id -> BatterInnings
    bowler_spells: dict = field(default_factory=dict)  # player_id -> BowlerSpell

    striker_id: Optional[int] = None
    non_striker_id: Optional[int] = None
    current_bowler_id: Optional[int] = None
    last_bowler_id: Optional[int] = None

    batting_order: list = field(default_factory=list)
    next_batter_index: int = 2  # 0 and 1 are openers

    extras: int = 0

    @property
    def overs_display(self) -> str:
        return f"{self.overs}.{self.balls}"

    @property
    def run_rate(self) -> float:
        total_balls = self.overs * 6 + self.balls
        if total_balls == 0:
            return 0.0
        return (self.total_runs / total_balls) * 6

    @property
    def required_rate(self) -> Optional[float]:
        if self.target is None:
            return None
        remaining = self.target - self.total_runs
        balls_left = (20 * 6) - (self.overs * 6 + self.balls)
        if balls_left <= 0:
            return 99.99
        return (remaining / balls_left) * 6

    @property
    def is_innings_complete(self) -> bool:
        if self.wickets >= 10:
            return True
        if self.overs >= 20:
            return True
        if self.target and self.total_runs >= self.target:
            return True
        return False


class MatchEngine:
    """
    Cricket match simulation engine.
    Simulates T20 matches ball by ball with probability-based outcomes.
    """

    # Base probabilities for outcomes (will be modified by player skills)
    BASE_PROBS = {
        "dot": 0.35,
        "single": 0.30,
        "two": 0.10,
        "three": 0.02,
        "four": 0.12,
        "six": 0.05,
        "wicket": 0.04,
        "wide": 0.015,
        "no_ball": 0.005,
    }

    DISMISSAL_TYPES = [
        ("bowled", 0.20),
        ("caught", 0.50),
        ("lbw", 0.15),
        ("caught_behind", 0.10),
        ("run_out", 0.03),
        ("stumped", 0.02),
    ]

    def __init__(self):
        self.innings1: Optional[InningsState] = None
        self.innings2: Optional[InningsState] = None
        self.current_innings: Optional[InningsState] = None

    def _calculate_outcome_probabilities(
        self,
        batter: Player,
        bowler: Player,
        innings_state: InningsState,
    ) -> dict[str, float]:
        """
        Calculate ball outcome probabilities based on player attributes and match situation.
        """
        probs = self.BASE_PROBS.copy()

        # Batter skill impact
        bat_skill = batter.batting / 100
        power_factor = batter.power / 100
        technique_factor = batter.technique / 100

        # Bowler skill impact
        bowl_skill = bowler.bowling / 100
        accuracy_factor = bowler.accuracy / 100
        variation_factor = bowler.variation / 100

        # Form multipliers
        bat_form = batter.form
        bowl_form = bowler.form

        # Effective skill difference (positive = batter advantage)
        skill_diff = (bat_skill * bat_form) - (bowl_skill * bowl_form)

        # Adjust probabilities based on skill difference
        # Better batters hit more boundaries, fewer dots, fewer wickets
        # Better bowlers get more dots, more wickets, fewer boundaries

        probs["dot"] = probs["dot"] * (1 - skill_diff * 0.3) * (1 + accuracy_factor * 0.2)
        probs["single"] = probs["single"] * (1 + technique_factor * 0.2)
        probs["two"] = probs["two"] * (1 + technique_factor * 0.1)
        probs["four"] = probs["four"] * (1 + skill_diff * 0.4) * (1 + power_factor * 0.3)
        probs["six"] = probs["six"] * (1 + skill_diff * 0.5) * (1 + power_factor * 0.5)
        probs["wicket"] = probs["wicket"] * (1 - skill_diff * 0.5) * (1 + variation_factor * 0.2)

        # Pressure situations
        if innings_state.target:
            required_rate = innings_state.required_rate or 0
            if required_rate > 12:
                # High pressure - more risks, more wickets, more sixes
                probs["six"] *= 1.5
                probs["wicket"] *= 1.3
                probs["dot"] *= 0.8
            elif required_rate > 9:
                probs["four"] *= 1.2
                probs["six"] *= 1.2

        # Death overs (16-20) - more boundaries and wickets
        if innings_state.overs >= 15:
            probs["four"] *= 1.3
            probs["six"] *= 1.4
            probs["wicket"] *= 1.1
            probs["dot"] *= 0.8

        # Powerplay (1-6) - more boundaries, slightly fewer wickets
        elif innings_state.overs < 6:
            probs["four"] *= 1.2
            probs["six"] *= 1.1
            probs["wicket"] *= 0.9

        # Bowling type specific adjustments
        if bowler.bowling_type == BowlingType.PACE:
            probs["four"] *= 1.1  # Pace is easier to hit for 4
            probs["lbw_chance"] = 0.2
        elif bowler.bowling_type in [BowlingType.LEG_SPIN, BowlingType.OFF_SPIN, BowlingType.LEFT_ARM_SPIN]:
            probs["six"] *= 1.15  # Spin easier to hit for 6 if read
            probs["stumped_chance"] = 0.1

        # Normalize probabilities
        total = sum(probs.values())
        probs = {k: v / total for k, v in probs.items()}

        return probs

    def _simulate_ball(
        self,
        batter: Player,
        bowler: Player,
        innings_state: InningsState,
        fielders: list[Player],
    ) -> BallOutcome:
        """Simulate a single ball delivery"""

        # Check for extras first
        if random.random() < self.BASE_PROBS["wide"]:
            return BallOutcome(
                runs=1,
                is_wide=True,
                commentary="Wide ball, 1 run added"
            )

        if random.random() < self.BASE_PROBS["no_ball"]:
            # No ball can still be hit
            runs = random.choices([0, 1, 2, 4, 6], weights=[0.3, 0.3, 0.1, 0.2, 0.1])[0]
            return BallOutcome(
                runs=runs + 1,
                is_no_ball=True,
                is_boundary=runs == 4,
                is_six=runs == 6,
                commentary=f"No ball! {runs + 1} runs"
            )

        # Calculate outcome probabilities
        probs = self._calculate_outcome_probabilities(batter, bowler, innings_state)

        # Select outcome
        outcomes = list(probs.keys())
        weights = list(probs.values())
        outcome = random.choices(outcomes, weights=weights)[0]

        ball_outcome = BallOutcome()

        if outcome == "dot":
            ball_outcome.runs = 0
            ball_outcome.commentary = f"{batter.name} defends, no run"

        elif outcome == "single":
            ball_outcome.runs = 1
            ball_outcome.commentary = f"{batter.name} pushes for a single"

        elif outcome == "two":
            ball_outcome.runs = 2
            ball_outcome.commentary = f"{batter.name} finds the gap, comes back for two"

        elif outcome == "three":
            ball_outcome.runs = 3
            ball_outcome.commentary = f"Good running! {batter.name} gets three"

        elif outcome == "four":
            ball_outcome.runs = 4
            ball_outcome.is_boundary = True
            shots = ["drives", "cuts", "pulls", "flicks", "sweeps"]
            ball_outcome.commentary = f"FOUR! {batter.name} {random.choice(shots)} it to the boundary"

        elif outcome == "six":
            ball_outcome.runs = 6
            ball_outcome.is_six = True
            ball_outcome.is_boundary = True
            shots = ["launches", "smashes", "lofts", "heaves", "slog-sweeps"]
            ball_outcome.commentary = f"SIX! {batter.name} {random.choice(shots)} it into the stands!"

        elif outcome == "wicket":
            ball_outcome.is_wicket = True
            ball_outcome.runs = 0

            # Determine dismissal type
            dismissal = random.choices(
                [d[0] for d in self.DISMISSAL_TYPES],
                weights=[d[1] for d in self.DISMISSAL_TYPES]
            )[0]

            ball_outcome.dismissal_type = dismissal

            if dismissal == "bowled":
                ball_outcome.commentary = f"BOWLED! {bowler.name} cleans up {batter.name}!"
            elif dismissal == "caught":
                fielder = random.choice(fielders) if fielders else None
                fielder_name = fielder.name if fielder else "a fielder"
                ball_outcome.commentary = f"CAUGHT! {batter.name} holes out to {fielder_name} off {bowler.name}!"
            elif dismissal == "lbw":
                ball_outcome.commentary = f"LBW! {bowler.name} traps {batter.name} in front!"
            elif dismissal == "caught_behind":
                ball_outcome.commentary = f"CAUGHT BEHIND! {batter.name} edges to the keeper off {bowler.name}!"
            elif dismissal == "run_out":
                ball_outcome.runs = random.choice([0, 1])
                ball_outcome.commentary = f"RUN OUT! {batter.name} is short of the crease!"
            elif dismissal == "stumped":
                ball_outcome.commentary = f"STUMPED! {batter.name} beaten by {bowler.name}'s flight!"

        return ball_outcome

    def setup_innings(
        self,
        batting_team: list[Player],
        bowling_team: list[Player],
        target: Optional[int] = None,
    ) -> InningsState:
        """Initialize an innings"""

        # Sort batters by role (proper batting order)
        batting_order = sorted(batting_team, key=lambda p: (
            0 if p.role == PlayerRole.WICKET_KEEPER else
            1 if p.role == PlayerRole.BATSMAN else
            2 if p.role == PlayerRole.ALL_ROUNDER else 3,
            -p.batting
        ))

        innings = InningsState(
            batting_team=batting_team,
            bowling_team=bowling_team,
            target=target,
            batting_order=[p.id for p in batting_order],
        )

        # Set openers
        innings.striker_id = batting_order[0].id
        innings.non_striker_id = batting_order[1].id

        # Initialize batter innings
        innings.batter_innings[batting_order[0].id] = BatterInnings(player=batting_order[0])
        innings.batter_innings[batting_order[1].id] = BatterInnings(player=batting_order[1])

        return innings

    def select_bowler(self, innings: InningsState) -> Player:
        """Select next bowler (cannot be same as last over, max 4 overs per bowler)"""
        bowlers = [p for p in innings.bowling_team if p.role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER]]

        # Filter out last bowler and those who have bowled 4 overs
        available = []
        for b in bowlers:
            spell = innings.bowler_spells.get(b.id)
            if spell and spell.overs >= 4:
                continue
            if b.id == innings.last_bowler_id:
                continue
            available.append(b)

        if not available:
            # Fallback: allow any bowler except last
            available = [b for b in bowlers if b.id != innings.last_bowler_id]

        if not available:
            available = bowlers

        # Weighted selection by bowling skill
        weights = [b.bowling for b in available]
        return random.choices(available, weights=weights)[0]

    def simulate_over(self, innings: InningsState) -> list[BallOutcome]:
        """Simulate a single over"""
        outcomes = []
        balls_bowled = 0

        # Select bowler
        bowler = self.select_bowler(innings)
        innings.current_bowler_id = bowler.id

        # Initialize bowler spell if needed
        if bowler.id not in innings.bowler_spells:
            innings.bowler_spells[bowler.id] = BowlerSpell(player=bowler)

        # Get fielders (excluding bowler and keeper)
        fielders = [p for p in innings.bowling_team if p.id != bowler.id]

        while balls_bowled < 6 and not innings.is_innings_complete:
            # Get current batter
            striker = next(p for p in innings.batting_team if p.id == innings.striker_id)

            # Simulate ball
            outcome = self._simulate_ball(striker, bowler, innings, fielders)
            outcomes.append(outcome)

            # Update innings state
            if not outcome.is_wide and not outcome.is_no_ball:
                balls_bowled += 1
                innings.balls += 1

                # Update batter
                batter_innings = innings.batter_innings[striker.id]
                batter_innings.balls += 1
                batter_innings.runs += outcome.runs
                if outcome.is_boundary and not outcome.is_six:
                    batter_innings.fours += 1
                if outcome.is_six:
                    batter_innings.sixes += 1

            # Update bowler spell
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

            # Update total
            innings.total_runs += outcome.runs

            # Handle wicket
            if outcome.is_wicket:
                innings.wickets += 1
                batter_innings = innings.batter_innings[innings.striker_id]
                batter_innings.is_out = True
                batter_innings.dismissal = outcome.dismissal_type
                batter_innings.bowler = bowler

                spell.wickets += 1

                # Bring in next batter
                if innings.next_batter_index < len(innings.batting_order):
                    next_batter_id = innings.batting_order[innings.next_batter_index]
                    next_batter = next(p for p in innings.batting_team if p.id == next_batter_id)
                    innings.striker_id = next_batter_id
                    innings.batter_innings[next_batter_id] = BatterInnings(player=next_batter)
                    innings.next_batter_index += 1

            # Rotate strike on odd runs
            elif outcome.runs % 2 == 1:
                innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id

            if innings.balls >= 6:
                innings.overs += 1
                innings.balls = 0
                spell.overs += 1
                spell.balls = 0
                innings.last_bowler_id = bowler.id
                # Rotate strike at end of over
                innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id
                break

        return outcomes

    def simulate_innings(self, innings: InningsState) -> InningsState:
        """Simulate a complete innings"""
        while not innings.is_innings_complete:
            self.simulate_over(innings)
        return innings

    def simulate_match(
        self,
        team1_players: list[Player],
        team2_players: list[Player],
        team1_bats_first: bool = True,
    ) -> dict:
        """
        Simulate a complete T20 match.

        Returns match result summary.
        """
        if team1_bats_first:
            first_batting = team1_players
            second_batting = team2_players
        else:
            first_batting = team2_players
            second_batting = team1_players

        # First innings
        self.innings1 = self.setup_innings(first_batting, second_batting)
        self.innings1 = self.simulate_innings(self.innings1)

        # Second innings
        target = self.innings1.total_runs + 1
        self.innings2 = self.setup_innings(second_batting, first_batting, target=target)
        self.innings2 = self.simulate_innings(self.innings2)

        # Determine result
        if self.innings2.total_runs >= target:
            winner = "team2" if team1_bats_first else "team1"
            margin = f"{10 - self.innings2.wickets} wickets"
            balls_remaining = (20 * 6) - (self.innings2.overs * 6 + self.innings2.balls)
            if balls_remaining > 0:
                margin += f" ({balls_remaining} balls remaining)"
        elif self.innings2.total_runs < target - 1:
            winner = "team1" if team1_bats_first else "team2"
            margin = f"{(target - 1) - self.innings2.total_runs} runs"
        else:
            winner = "tie"
            margin = "Match tied!"

        return {
            "innings1": {
                "runs": self.innings1.total_runs,
                "wickets": self.innings1.wickets,
                "overs": self.innings1.overs_display,
                "run_rate": round(self.innings1.run_rate, 2),
            },
            "innings2": {
                "runs": self.innings2.total_runs,
                "wickets": self.innings2.wickets,
                "overs": self.innings2.overs_display,
                "run_rate": round(self.innings2.run_rate, 2),
            },
            "winner": winner,
            "margin": margin,
        }
