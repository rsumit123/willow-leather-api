import random
import json
from faker import Faker
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle, PlayerTrait, BattingIntent
from app.database import get_session

# Initialize Faker instances - use en_US as fallback for unavailable locales
fake_in = Faker('en_IN')
fake_au = Faker('en_AU')
fake_en = Faker('en_GB')
fake_za = Faker('en_US')  # en_ZA not available, using en_US
fake_nz = Faker('en_NZ')
fake_wi = Faker('en_US')  # No specific WI locale


class PlayerGenerator:
    """Generates fictional cricket players with realistic attributes"""

    # Nationality distribution (weighted towards Indian players for IPL)
    NATIONALITIES = [
        ("India", fake_in, False, 60),
        ("Australia", fake_au, True, 10),
        ("England", fake_en, True, 8),
        ("South Africa", fake_za, True, 7),
        ("New Zealand", fake_nz, True, 5),
        ("West Indies", fake_wi, True, 5),
        ("Other", fake_en, True, 5),
    ]

    # Role distribution
    ROLE_WEIGHTS = {
        PlayerRole.BATSMAN: 30,
        PlayerRole.BOWLER: 35,
        PlayerRole.ALL_ROUNDER: 20,
        PlayerRole.WICKET_KEEPER: 15,
    }

    # Bowling type distribution by role
    BOWLING_TYPES = {
        PlayerRole.BOWLER: [
            (BowlingType.PACE, 40),
            (BowlingType.MEDIUM, 15),
            (BowlingType.OFF_SPIN, 20),
            (BowlingType.LEG_SPIN, 15),
            (BowlingType.LEFT_ARM_SPIN, 10),
        ],
        PlayerRole.ALL_ROUNDER: [
            (BowlingType.PACE, 30),
            (BowlingType.MEDIUM, 25),
            (BowlingType.OFF_SPIN, 25),
            (BowlingType.LEG_SPIN, 10),
            (BowlingType.LEFT_ARM_SPIN, 10),
        ],
    }

    # Trait pools by role (kept for reference, weights below control distribution)
    TRAIT_POOLS = {
        PlayerRole.BATSMAN: [
            PlayerTrait.CLUTCH,
            PlayerTrait.CHOKER,
            PlayerTrait.FINISHER
        ],
        PlayerRole.BOWLER: [
            PlayerTrait.CLUTCH,
            PlayerTrait.CHOKER,
            PlayerTrait.PARTNERSHIP_BREAKER
        ],
        PlayerRole.ALL_ROUNDER: [
            PlayerTrait.CLUTCH,
            PlayerTrait.CHOKER,
            PlayerTrait.FINISHER,
            PlayerTrait.PARTNERSHIP_BREAKER
        ],
        PlayerRole.WICKET_KEEPER: [
            PlayerTrait.CLUTCH,
            PlayerTrait.CHOKER,
            PlayerTrait.BUCKET_HANDS
        ],
    }

    # === BALANCED DISTRIBUTION CONSTANTS ===

    # Batting Intent Target Distribution (for non-bowlers)
    # ACCUMULATOR: 50% - steady players, most common
    # ANCHOR: 25% - valuable stabilizers
    # AGGRESSIVE: 18% - impact players
    # POWER_HITTER: 7% - rare match-winners
    BATTING_INTENT_WEIGHTS = {
        BattingIntent.ACCUMULATOR: 50,
        BattingIntent.ANCHOR: 25,
        BattingIntent.AGGRESSIVE: 18,
        BattingIntent.POWER_HITTER: 7,
    }

    # Trait count weights by tier [0 traits, 1 trait, 2 traits]
    # Elite players more likely to have positive traits
    # Solid players mostly "normal"
    # Reduced 2-trait probability across all tiers
    TRAIT_COUNT_WEIGHTS = {
        "elite": [35, 50, 15],   # 65% have at least one trait
        "star": [50, 40, 10],    # 50% have at least one trait
        "good": [60, 33, 7],     # 40% have at least one trait
        "solid": [70, 27, 3],    # 30% have at least one trait
    }

    # Trait weights by role (relative weights for selection)
    # Lower weights = rarer traits (more special)
    # Higher weights = more common traits
    TRAIT_WEIGHTS = {
        PlayerRole.BATSMAN: {
            PlayerTrait.CLUTCH: 8,       # Ultra rare - performs under pressure
            PlayerTrait.FINISHER: 10,    # Very rare - death overs specialist
            PlayerTrait.CHOKER: 35,      # Negative trait, more common
        },
        PlayerRole.BOWLER: {
            PlayerTrait.CLUTCH: 8,       # Ultra rare
            PlayerTrait.PARTNERSHIP_BREAKER: 15,  # Uncommon - breaks stands
            PlayerTrait.CHOKER: 35,      # Negative trait
        },
        PlayerRole.ALL_ROUNDER: {
            PlayerTrait.CLUTCH: 8,       # Ultra rare
            PlayerTrait.FINISHER: 10,    # Very rare
            PlayerTrait.PARTNERSHIP_BREAKER: 12,  # Uncommon
            PlayerTrait.CHOKER: 30,      # Negative trait
        },
        PlayerRole.WICKET_KEEPER: {
            PlayerTrait.CLUTCH: 8,       # Ultra rare
            PlayerTrait.BUCKET_HANDS: 28,  # Common for keepers
            PlayerTrait.CHOKER: 30,      # Negative trait
        },
    }

    # Reduce CHOKER chance for higher tier players (elite players handle pressure)
    # These are multipliers applied to CHOKER weight
    CHOKER_REDUCTION = {
        "elite": 0.10,  # 90% reduction - elite players rarely choke
        "star": 0.35,   # 65% reduction
        "good": 0.65,   # 35% reduction
        "solid": 1.0,   # No reduction - newer players more prone
    }

    # Minimum stats required for certain intents (validation)
    INTENT_REQUIREMENTS = {
        BattingIntent.POWER_HITTER: {"power": 55},  # Need decent power
        BattingIntent.ANCHOR: {"technique": 45},     # Need some technique
    }

    @staticmethod
    def _weighted_choice(choices: list[tuple]) -> any:
        """Select from weighted choices [(item, weight), ...]"""
        items = [c[0] for c in choices]
        weights = [c[1] for c in choices]
        return random.choices(items, weights=weights, k=1)[0]

    @staticmethod
    def _generate_attribute(base: int, variance: int = 15, minimum: int = 1) -> int:
        """Generate an attribute value with some variance"""
        value = base + random.randint(-variance, variance)
        return max(minimum, min(100, value))  # Clamp between minimum-100

    @classmethod
    def _determine_batting_intent(cls, power: int, technique: int, role: PlayerRole) -> BattingIntent:
        """
        Determine batting intent with controlled distribution.
        Uses weighted random selection to ensure proper rarity of special intents.

        Distribution (non-bowlers):
        - ACCUMULATOR: 50% - steady, reliable players
        - ANCHOR: 25% - stabilizers who build innings
        - AGGRESSIVE: 18% - impact players
        - POWER_HITTER: 7% - rare match-winners
        """
        # Bowlers are always accumulators (they just try to survive)
        if role == PlayerRole.BOWLER:
            return BattingIntent.ACCUMULATOR

        # Use weighted random selection for controlled distribution
        intents = list(cls.BATTING_INTENT_WEIGHTS.keys())
        weights = list(cls.BATTING_INTENT_WEIGHTS.values())
        selected = random.choices(intents, weights=weights)[0]

        # Validate: Power hitters need minimum power to be credible
        if selected == BattingIntent.POWER_HITTER:
            min_power = cls.INTENT_REQUIREMENTS.get(BattingIntent.POWER_HITTER, {}).get("power", 55)
            if power < min_power:
                # Downgrade to aggressive if not powerful enough
                return BattingIntent.AGGRESSIVE

        # Validate: Anchors need minimum technique
        if selected == BattingIntent.ANCHOR:
            min_technique = cls.INTENT_REQUIREMENTS.get(BattingIntent.ANCHOR, {}).get("technique", 45)
            if technique < min_technique:
                # Downgrade to accumulator if no technique
                return BattingIntent.ACCUMULATOR

        return selected

    @classmethod
    def _assign_traits(cls, role: PlayerRole, tier: str) -> list[PlayerTrait]:
        """
        Assign traits with weighted probability based on role and tier.

        - Higher tier players more likely to have positive traits
        - CHOKER trait less likely for elite/star players
        - Each role has specific trait weights

        Returns list of 0-2 traits.
        """
        # Determine number of traits based on tier
        count_weights = cls.TRAIT_COUNT_WEIGHTS.get(tier, [55, 35, 10])
        num_traits = random.choices([0, 1, 2], weights=count_weights)[0]

        if num_traits == 0:
            return []

        # Get trait weights for this role
        role_weights = cls.TRAIT_WEIGHTS.get(role, {})
        if not role_weights:
            return []

        # Apply CHOKER reduction for higher tier players
        choker_mult = cls.CHOKER_REDUCTION.get(tier, 1.0)

        # Build weighted trait pool
        trait_pool = []
        weight_pool = []

        for trait, weight in role_weights.items():
            # Reduce CHOKER chance for better players
            if trait == PlayerTrait.CHOKER:
                weight = int(weight * choker_mult)

            if weight > 0:
                trait_pool.append(trait)
                weight_pool.append(weight)

        if not trait_pool:
            return []

        # Select traits without duplicates
        traits = []
        available_traits = list(zip(trait_pool, weight_pool))

        for _ in range(num_traits):
            if not available_traits:
                break

            # Select one trait
            traits_list = [t for t, w in available_traits]
            weights_list = [w for t, w in available_traits]

            selected = random.choices(traits_list, weights=weights_list)[0]
            traits.append(selected)

            # Remove selected trait from pool (no duplicates)
            available_traits = [(t, w) for t, w in available_traits if t != selected]

        return traits

    @staticmethod
    def _ensure_minimum_ovr(player: Player, min_ovr: int = 55) -> Player:
        """
        Ensure a player has at least the minimum OVR by boosting primary attributes.
        """
        while player.overall_rating < min_ovr:
            diff = min_ovr - player.overall_rating + 2  # Add a small buffer
            # Boost primary attribute based on role
            if player.role == PlayerRole.BATSMAN:
                player.batting = min(100, player.batting + diff)
            elif player.role == PlayerRole.BOWLER:
                player.bowling = min(100, player.bowling + diff)
            elif player.role == PlayerRole.ALL_ROUNDER:
                boost = diff // 2 + 1
                player.batting = min(100, player.batting + boost)
                player.bowling = min(100, player.bowling + boost)
            elif player.role == PlayerRole.WICKET_KEEPER:
                boost_bat = (diff * 5) // 9 + 1
                boost_field = (diff * 4) // 9 + 1
                player.batting = min(100, player.batting + boost_bat)
                player.fielding = min(100, player.fielding + boost_field)
        return player

    @classmethod
    def generate_player(cls, role: PlayerRole = None, nationality: str = None, tier: str = "average") -> Player:
        """
        Generate a single player.

        Args:
            role: Specific role, or random if None
            nationality: Specific nationality, or weighted random if None
            tier: "star" (70-90 base), "good" (55-75 base), "average" (40-60 base), "developing" (25-45 base)
        """
        # Determine nationality
        if nationality is None:
            nat_choice = cls._weighted_choice([(n[0], n[3]) for n in cls.NATIONALITIES])
            nat_data = next(n for n in cls.NATIONALITIES if n[0] == nat_choice)
        else:
            nat_data = next((n for n in cls.NATIONALITIES if n[0] == nationality), cls.NATIONALITIES[0])

        nationality_name, faker_instance, is_overseas, _ = nat_data

        # Determine role
        if role is None:
            role = cls._weighted_choice(list(cls.ROLE_WEIGHTS.items()))

        # Determine batting style (slight right-hand bias)
        batting_style = random.choices(
            [BattingStyle.RIGHT_HANDED, BattingStyle.LEFT_HANDED],
            weights=[70, 30],
            k=1
        )[0]

        # Determine bowling type
        if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER]:
            bowling_type = cls._weighted_choice(cls.BOWLING_TYPES[role])
        else:
            # Part-timers get random medium or spin
            bowling_type = random.choice([
                BowlingType.MEDIUM,
                BowlingType.OFF_SPIN,
                BowlingType.LEG_SPIN,
                BowlingType.LEFT_ARM_SPIN
            ])

        # Base attributes by tier (adjusted to ensure 55+ OVR)
        # OVR formula uses weighted average, variance can push down by ~8-10 points
        # So base needs to be 8-10 higher than target OVR minimum
        tier_bases = {
            "elite": random.randint(80, 90),    # OVR ~85-95
            "star": random.randint(70, 80),     # OVR ~75-85
            "good": random.randint(62, 72),     # OVR ~65-75
            "solid": random.randint(58, 65),    # OVR ~55-68 (ensures 55+ minimum)
        }
        base = tier_bases.get(tier, tier_bases["solid"])

        # Generate attributes based on role
        if role == PlayerRole.BATSMAN:
            batting = cls._generate_attribute(base + 10, 10)
            bowling = cls._generate_attribute(20, 10)
            power = cls._generate_attribute(base, 15)
            technique = cls._generate_attribute(base, 15)
        elif role == PlayerRole.BOWLER:
            batting = cls._generate_attribute(30, 15)
            bowling = cls._generate_attribute(base + 10, 10)
            power = cls._generate_attribute(30, 10)
            technique = cls._generate_attribute(30, 10)
        elif role == PlayerRole.ALL_ROUNDER:
            batting = cls._generate_attribute(base, 12)
            bowling = cls._generate_attribute(base, 12)
            power = cls._generate_attribute(base - 5, 15)
            technique = cls._generate_attribute(base - 5, 15)
        else:  # Wicket keeper
            batting = cls._generate_attribute(base, 12)
            bowling = cls._generate_attribute(15, 10)
            power = cls._generate_attribute(base - 10, 15)
            technique = cls._generate_attribute(base + 5, 10)

        # Common attributes
        fielding = cls._generate_attribute(base if role != PlayerRole.WICKET_KEEPER else base + 15, 15)
        fitness = cls._generate_attribute(base, 15)
        running = cls._generate_attribute(base, 15)
        temperament = cls._generate_attribute(base, 20)
        consistency = cls._generate_attribute(base, 15)

        # Bowling sub-attributes (more relevant for bowlers)
        if role in [PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER]:
            pace_or_spin = cls._generate_attribute(base + 5, 15)
            accuracy = cls._generate_attribute(base, 15)
            variation = cls._generate_attribute(base - 5, 15)
        else:
            pace_or_spin = cls._generate_attribute(20, 10)
            accuracy = cls._generate_attribute(20, 10)
            variation = cls._generate_attribute(15, 10)

        # Age based on tier
        if tier == "elite":
            age = random.randint(27, 34)
        elif tier == "star":
            age = random.randint(25, 33)
        elif tier == "good":
            age = random.randint(23, 31)
        else:  # solid
            age = random.randint(21, 29)

        # Assign 0-2 traits using weighted distribution based on role and tier
        traits = cls._assign_traits(role, tier)
        traits_json = json.dumps([t.value for t in traits])

        # Determine batting intent based on power vs technique
        batting_intent = cls._determine_batting_intent(power, technique, role)

        # Base price based on tier and role
        base_prices = {
            "elite": random.randint(15000000, 25000000),   # 1.5-2.5 crore
            "star": random.randint(10000000, 15000000),    # 1-1.5 crore
            "good": random.randint(5000000, 10000000),     # 50L-1 crore
            "solid": random.randint(2000000, 5000000),     # 20L-50L
        }
        base_price = base_prices.get(tier, 2000000)

        # Create player
        player = Player(
            name=faker_instance.name_male(),
            age=age,
            nationality=nationality_name,
            is_overseas=is_overseas,
            role=role,
            batting_style=batting_style,
            bowling_type=bowling_type,
            batting=batting,
            bowling=bowling,
            fielding=fielding,
            fitness=fitness,
            power=power,
            technique=technique,
            running=running,
            pace_or_spin=pace_or_spin,
            accuracy=accuracy,
            variation=variation,
            temperament=temperament,
            consistency=consistency,
            form=round(random.uniform(0.9, 1.1), 2),
            traits=traits_json,
            batting_intent=batting_intent.value,
            base_price=base_price,
        )

        # Ensure minimum OVR of 55
        player = cls._ensure_minimum_ovr(player, min_ovr=55)

        return player

    @classmethod
    def _random_overseas_nationality(cls) -> str:
        """Get a random overseas nationality (non-India)."""
        overseas = [n for n in cls.NATIONALITIES if n[2]]  # is_overseas=True
        return cls._weighted_choice([(n[0], n[3]) for n in overseas])

    @classmethod
    def generate_player_pool(cls, count: int = 230) -> list[Player]:
        """
        Generate a pool of players for the auction.
        Target: 230 players (25 per team * 8 teams + 30 buffer), all with 55+ OVR.
        Distribution: ~20 elite, ~40 star, ~80 good, ~90 solid
        Overseas: ~80 players (enough for 8 per team * 8 teams + buffer)
        """
        players = []

        # Generate elite players (20 total: 8 Indian, 12 overseas)
        for _ in range(8):
            players.append(cls.generate_player(tier="elite", nationality="India"))
        for _ in range(12):
            players.append(cls.generate_player(tier="elite", nationality=cls._random_overseas_nationality()))

        # Generate star players (40 total: 18 Indian, 22 overseas)
        for _ in range(18):
            players.append(cls.generate_player(tier="star", nationality="India"))
        for _ in range(22):
            players.append(cls.generate_player(tier="star", nationality=cls._random_overseas_nationality()))

        # Generate good players (80 total: 50 Indian, 30 overseas)
        for _ in range(50):
            players.append(cls.generate_player(tier="good", nationality="India"))
        for _ in range(30):
            players.append(cls.generate_player(tier="good", nationality=cls._random_overseas_nationality()))

        # Generate solid players (90 total: 74 Indian, 16 overseas)
        for _ in range(74):
            players.append(cls.generate_player(tier="solid", nationality="India"))
        for _ in range(16):
            players.append(cls.generate_player(tier="solid", nationality=cls._random_overseas_nationality()))

        # Total: 230 players (150 Indian, 80 overseas)
        return players

    @classmethod
    def save_players_to_db(cls, players: list[Player]) -> None:
        """Save generated players to database"""
        session = get_session()
        try:
            for player in players:
                session.add(player)
            session.commit()
        finally:
            session.close()
