import random
import json
from dataclasses import dataclass, field
from typing import Optional, List
from app.models.player import Player, PlayerRole, BowlingType, PlayerTrait


@dataclass
class MatchContext:
    """Dynamic match context affecting all calculations"""
    pitch_type: str = "flat_deck"  # "green_top", "dust_bowl", "flat_deck"
    is_pressure_cooker: bool = False  # RRR > 12 or wickets < 3
    partnership_runs: int = 0


@dataclass
class BatterState:
    """Extended batter state with status effects"""
    player_id: int
    balls_faced: int = 0
    is_settled: bool = False  # > 15 balls
    is_on_fire: bool = False  # 2 boundaries in last 3 balls
    recent_outcomes: list = field(default_factory=list)


@dataclass
class BowlerState:
    """Extended bowler state"""
    player_id: int
    consecutive_overs: int = 0
    is_tired: bool = False  # > 4 consecutive overs
    has_confidence: bool = False  # took wicket last over


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

    # Interactive match states
    context: MatchContext = field(default_factory=MatchContext)
    batter_states: dict = field(default_factory=dict)  # player_id -> BatterState
    bowler_states: dict = field(default_factory=dict)  # player_id -> BowlerState
    this_over: list = field(default_factory=list)  # list of outcomes for current over

    extras: int = 0
    batting_team_id: Optional[int] = None

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

    def _get_pitch_modifier(self, bowler: Player, pitch_type: str) -> int:
        """Calculate skill modifier based on pitch and bowling style - REDUCED for balance"""
        if pitch_type == "green_top":
            if bowler.bowling_type == BowlingType.PACE:
                return 3  # Reduced from 8 - was causing 19% wicket rate!
            if bowler.bowling_type == BowlingType.MEDIUM:
                return 4
            if "spin" in bowler.bowling_type.value:
                return -3
        elif pitch_type == "dust_bowl":
            if "spin" in bowler.bowling_type.value:
                return 4
            if bowler.bowling_type == BowlingType.PACE:
                return -2
        elif pitch_type == "flat_deck":
            return -2  # Slight advantage for batters
        return 0

    def _apply_batter_traits(self, batter: Player, context: MatchContext, state: BatterState) -> int:
        """Apply batter traits to roll"""
        if not batter.traits:
            return 0
        
        traits = json.loads(batter.traits)
        bonus = 0
        
        if PlayerTrait.CLUTCH.value in traits and context.is_pressure_cooker:
            bonus += 10
        if PlayerTrait.CHOKER.value in traits and context.is_pressure_cooker:
            bonus -= 15
        if PlayerTrait.FINISHER.value in traits and context.is_pressure_cooker:
            bonus += 15  # Simplified: Finisher works in pressure/death
            
        return bonus

    def _apply_bowler_traits(self, bowler: Player, context: MatchContext) -> int:
        """Apply bowler traits to difficulty"""
        if not bowler.traits:
            return 0

        traits = json.loads(bowler.traits)
        bonus = 0

        if PlayerTrait.CLUTCH.value in traits and context.is_pressure_cooker:
            bonus += 10
        if PlayerTrait.CHOKER.value in traits and context.is_pressure_cooker:
            bonus -= 15
        if PlayerTrait.PARTNERSHIP_BREAKER.value in traits and context.partnership_runs >= 50:
            bonus += 10

        return bonus

    def _get_run_rate_adjustment(self, innings: InningsState) -> int:
        """Apply run rate floor/ceiling to prevent extreme scores (50-260)"""
        total_balls = innings.overs * 6 + innings.balls
        if total_balls < 12:  # First 2 overs, no adjustment
            return 0

        current_rr = innings.total_runs / (total_balls / 6) if total_balls > 0 else 0

        # Floor: 3.0 RR (60 runs in 20 overs) - help struggling batting
        # Progressive boost - the further below target, the stronger the boost
        if current_rr < 3.5 and innings.wickets < 8:
            deficit = 3.5 - current_rr
            return min(30, int(deficit * 12))  # Strong boost, capped at 30

        # Ceiling: 11 RR (220 runs in 20 overs) - start slowing down early
        # Progressive penalty - the further above target, the stronger the penalty
        if current_rr > 11:
            excess = current_rr - 11
            return max(-40, -int(excess * 10))  # Very strong penalty, capped at -40

        return 0

    def _get_wicket_protection(self, innings: InningsState) -> int:
        """Reduce wicket probability for losing teams and late-innings all-outs"""
        adjustment = 0

        # Protect struggling teams: if runs < 60 and low run rate
        if innings.total_runs < 60 and innings.wickets < 6:
            adjustment += 15  # Strong boost to reduce wicket chance

        # Extra protection when nearly all out early
        if innings.wickets >= 5 and innings.overs < 10:
            adjustment += 18  # Very strong protection

        # Wicket cap (soft): if wickets >= 7 before over 12, reduce wicket probability
        if innings.wickets >= 7 and innings.overs < 12:
            adjustment += 25  # Massive boost to prevent early all-outs

        return adjustment

    def calculate_ball_outcome(
        self,
        batter: Player,
        bowler: Player,
        aggression: str,  # "defend", "balanced", "attack"
        innings_state: InningsState,
    ) -> BallOutcome:
        """New interactive ball calculation system"""
        context = innings_state.context
        batter_state = innings_state.batter_states.setdefault(batter.id, BatterState(player_id=batter.id))
        bowler_state = innings_state.bowler_states.setdefault(bowler.id, BowlerState(player_id=bowler.id))

        # Step 1: Calculate Bowling Difficulty (The Target Score)
        # Scale bowling to 78% for balanced T20-like scoring rates
        bowling_difficulty = int(bowler.bowling * 0.78)
        bowling_difficulty += self._get_pitch_modifier(bowler, context.pitch_type)
        # REMOVED cascading bonuses - they caused 4+ wickets per over
        # Confidence and nervous bonuses were causing death spirals
        bowling_difficulty -= 3 if batter_state.is_settled else 0  # Small bonus for settled batters
        bowling_difficulty += self._apply_bowler_traits(bowler, context)

        # Step 2: The Batsman's Action (The Roll)
        # Defend: Lower variance (safer, fewer big shots, fewer wickets)
        # Balanced: Normal variance
        # Attack: Higher variance (more big shots possible, but also more wickets)
        skill_multiplier = {"defend": 0.7, "balanced": 1.0, "attack": 1.4}[aggression]

        # Base bonus for defend (safer), penalty for attack (riskier)
        base_adjustment = {"defend": 8, "balanced": 0, "attack": -5}[aggression]

        # CRITICAL FIX: Minimum effective batting to prevent tail-ender massacre
        # Even tail-enders can block and survive - they don't get out every ball
        # This prevents the 72% wicket rate we were seeing for low-order batters
        effective_batting = max(batter.batting, 55)  # Floor at 55 for wicket calculations

        # Give batter a baseline roll to make contests more even
        # Base is 1/3 of batting, variable portion is 2/3 * multiplier
        batting_base = effective_batting // 3 + base_adjustment
        batting_variable = int(effective_batting * 2 // 3 * skill_multiplier)
        batting_roll = batting_base + random.randint(0, batting_variable)
        batting_roll += self._apply_batter_traits(batter, context, batter_state)

        # Apply run rate governors to keep scores in 50-260 range
        batting_roll += self._get_run_rate_adjustment(innings_state)

        # Apply wicket protection for struggling teams
        batting_roll += self._get_wicket_protection(innings_state)

        final_difficulty = bowling_difficulty

        # Step 3: Compare & Resolve
        margin = batting_roll - final_difficulty

        # Dynamic boundary threshold based on run rate
        current_rr = innings_state.run_rate
        boundary_threshold = 18  # Base threshold (increased from 17)
        if current_rr > 12:
            boundary_threshold = 22  # Harder to hit boundaries when scoring fast

        outcome = BallOutcome()

        if margin >= 0:
            # Batsman Wins - good shots and boundaries
            attack_boundary_threshold = boundary_threshold - 8  # Lower threshold in attack mode
            if margin >= boundary_threshold or (aggression == "attack" and margin >= attack_boundary_threshold):
                # Boundary - threshold adjusted based on run rate
                is_six = random.random() < (batter.power / 170)
                outcome.runs = 6 if is_six else 4
                outcome.is_boundary = True
                outcome.is_six = is_six
                outcome.commentary = f"BOOM! {batter.name} hits it for {'SIX' if is_six else 'FOUR'}!"
            elif margin >= 6:
                outcome.runs = random.choice([2, 2, 3])
                outcome.commentary = f"Good shot! {batter.name} gets {outcome.runs} runs."
            else:
                outcome.runs = random.choice([0, 1, 1, 1])  # Singles with occasional dot
                outcome.commentary = f"{batter.name} pushes for {outcome.runs}." if outcome.runs else f"{batter.name} defends."
        else:
            # Bowler Wins - calibrated for ~3-5% wicket rate per ball
            margin_abs = abs(margin)

            if margin_abs >= 38:  # Increased from 34 for fewer clean wickets
                # Clean Wicket - batter completely beaten
                outcome.is_wicket = True
                outcome.dismissal_type = random.choice(["bowled", "lbw"])
                outcome.commentary = f"WICKET! {bowler.name} {'cleans him up' if outcome.dismissal_type == 'bowled' else 'traps him in front'}!"
            elif margin_abs >= 22:  # Edge zone now -22 to -38 (was -20 to -34)
                # Edge / Catch Chance - 25% catch success (reduced from 28%)
                if random.random() < 0.25:
                    outcome.is_wicket = True
                    outcome.dismissal_type = random.choice(["caught", "caught_behind"])
                    outcome.commentary = f"OUT! {batter.name} edges it to {'the keeper' if outcome.dismissal_type == 'caught_behind' else 'a fielder'}!"
                else:
                    # Beaten/dropped - can still get runs off edges
                    outcome.runs = random.choice([0, 0, 1, 1])
                    if random.random() < 0.25:
                        outcome.commentary = f"CHANCE! But the catch goes down!"
                    else:
                        outcome.commentary = f"{batter.name} is beaten but survives!"
            elif margin_abs >= 12:  # Increased from 10
                # Beaten but survives - mix of dots and singles
                outcome.runs = random.choice([0, 0, 1, 1, 1])
                outcome.commentary = f"{batter.name} is beaten but survives!" if outcome.runs == 0 else f"Pushed into a gap for a single!"
            else:
                # Close contest - bowler slightly ahead but batter rotates strike
                outcome.runs = random.choice([0, 1, 1, 1, 2])
                outcome.commentary = f"{batter.name} defends solidly." if outcome.runs == 0 else f"{batter.name} works it away for {outcome.runs}."

        return outcome

    def _simulate_ball(
        self,
        batter: Player,
        bowler: Player,
        innings_state: InningsState,
        fielders: list[Player],
        aggression: str = "balanced",
    ) -> BallOutcome:
        """Simulate a single ball delivery"""

        # Check for extras first
        # Simplified extras: 2% chance of wide/no ball
        extra_roll = random.random()
        if extra_roll < 0.015:
            return BallOutcome(
                runs=1,
                is_wide=True,
                commentary="Wide ball, 1 run added"
            )
        if extra_roll < 0.02:
            # No ball can still be hit
            runs = random.choices([0, 1, 2, 4, 6], weights=[0.3, 0.3, 0.1, 0.2, 0.1])[0]
            return BallOutcome(
                runs=runs + 1,
                is_no_ball=True,
                is_boundary=runs == 4,
                is_six=runs == 6,
                commentary=f"No ball! {runs + 1} runs"
            )

        # Calculate outcome using new calculation system
        return self.calculate_ball_outcome(batter, bowler, aggression, innings_state)

    def setup_innings(
        self,
        batting_team: list[Player],
        bowling_team: list[Player],
        target: Optional[int] = None,
    ) -> InningsState:
        """Initialize an innings"""

        # Sort batters by batting skill (bowlers bat last)
        batting_order = sorted(batting_team, key=lambda p: (
            1 if p.role == PlayerRole.BOWLER else 0,  # Bowlers bat last
            -p.batting  # Then by batting skill (highest first)
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

    def simulate_over(self, innings: InningsState, aggression: str = "balanced") -> list[BallOutcome]:
        """Simulate a single over"""
        outcomes = []
        balls_bowled = 0
        wickets_this_over = 0  # Track wickets to prevent unrealistic collapses

        # Use existing bowler selection if set (user selected), otherwise auto-select
        if innings.current_bowler_id:
            bowler = next(p for p in innings.bowling_team if p.id == innings.current_bowler_id)
        else:
            bowler = self.select_bowler(innings)
            innings.current_bowler_id = bowler.id

        # Initialize states if needed
        if bowler.id not in innings.bowler_states:
            innings.bowler_states[bowler.id] = BowlerState(player_id=bowler.id)

        # Initialize bowler spell if needed
        if bowler.id not in innings.bowler_spells:
            innings.bowler_spells[bowler.id] = BowlerSpell(player=bowler)

        # Get fielders (excluding bowler and keeper)
        fielders = [p for p in innings.bowling_team if p.id != bowler.id]

        innings.this_over = []

        while balls_bowled < 6 and not innings.is_innings_complete:
            # Get current batter
            striker = next(p for p in innings.batting_team if p.id == innings.striker_id)

            # Simulate ball
            outcome = self._simulate_ball(striker, bowler, innings, fielders, aggression)
            outcomes.append(outcome)
            innings.this_over.append(outcome)

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

                # Update batter state
                b_state = innings.batter_states[striker.id]
                b_state.balls_faced += 1
                b_state.is_settled = b_state.balls_faced > 15
                b_state.recent_outcomes.append(outcome)


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

            # Handle wicket - cap at 3 per over to prevent unrealistic collapses
            # In real cricket, 4+ wickets in an over is extremely rare (maybe a handful ever)
            if outcome.is_wicket:
                if wickets_this_over >= 3:
                    # Convert to a dot ball - batter survives
                    outcome.is_wicket = False
                    outcome.runs = 0
                    outcome.dismissal_type = ""
                    outcome.commentary = f"{striker.name} survives a close call!"
                else:
                    wickets_this_over += 1
                    innings.wickets += 1
                    batter_innings = innings.batter_innings[innings.striker_id]
                    batter_innings.is_out = True
                    batter_innings.dismissal = outcome.dismissal_type
                    batter_innings.bowler = bowler

                    spell.wickets += 1

                    # Update bowler confidence
                    innings.bowler_states[bowler.id].has_confidence = True

                    # Bring in next batter
                    if innings.next_batter_index < len(innings.batting_order):
                        next_batter_id = innings.batting_order[innings.next_batter_index]
                        next_batter = next(p for p in innings.batting_team if p.id == next_batter_id)
                        innings.striker_id = next_batter_id
                        innings.batter_innings[next_batter_id] = BatterInnings(player=next_batter)

                        # New batter state
                        innings.batter_states[next_batter_id] = BatterState(player_id=next_batter_id)

                        innings.next_batter_index += 1

            # Rotate strike on odd runs
            if not outcome.is_wicket and outcome.runs % 2 == 1:
                innings.striker_id, innings.non_striker_id = innings.non_striker_id, innings.striker_id

            if innings.balls >= 6:
                innings.overs += 1
                innings.balls = 0
                spell.overs += 1
                spell.balls = 0
                innings.last_bowler_id = bowler.id

                # Reset current bowler so next over requires selection
                innings.current_bowler_id = None

                # Update bowler state
                innings.bowler_states[bowler.id].consecutive_overs += 1
                innings.bowler_states[bowler.id].is_tired = innings.bowler_states[bowler.id].consecutive_overs > 4

                # Reset other bowlers consecutive overs if they didn't bowl this over
                # Actually, only reset if they were rested.

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
