import random
import json
from faker import Faker
from app.models.player import Player, PlayerRole, BowlingType, BattingStyle, PlayerTrait
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

    # Trait pools by role
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
            bowling_type = BowlingType.NONE

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

        # Assign 0-2 traits
        num_traits = random.choices([0, 1, 2], weights=[40, 40, 20])[0]
        traits = []
        if num_traits > 0:
            pool = cls.TRAIT_POOLS.get(role, [])
            if pool:
                traits = random.sample(pool, min(num_traits, len(pool)))
        
        traits_json = json.dumps([t.value for t in traits])

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
