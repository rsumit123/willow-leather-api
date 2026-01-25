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
    def _generate_attribute(base: int, variance: int = 15) -> int:
        """Generate an attribute value with some variance"""
        value = base + random.randint(-variance, variance)
        return max(1, min(100, value))  # Clamp between 1-100

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

        # Base attributes by tier
        tier_bases = {
            "star": random.randint(70, 85),
            "good": random.randint(55, 70),
            "average": random.randint(40, 55),
            "developing": random.randint(25, 40),
        }
        base = tier_bases.get(tier, tier_bases["average"])

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
        if tier == "star":
            age = random.randint(26, 34)
        elif tier == "good":
            age = random.randint(24, 32)
        elif tier == "developing":
            age = random.randint(18, 23)
        else:
            age = random.randint(22, 30)

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
            "star": random.randint(10000000, 20000000),
            "good": random.randint(5000000, 10000000),
            "average": random.randint(2000000, 5000000),
            "developing": random.randint(2000000, 3000000),
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

        return player

    @classmethod
    def generate_player_pool(cls, count: int = 150) -> list[Player]:
        """
        Generate a pool of players for the auction.
        Distribution: ~15 stars, ~35 good, ~60 average, ~40 developing
        """
        players = []

        # Generate star players (mix of Indian and overseas)
        for _ in range(5):
            players.append(cls.generate_player(tier="star", nationality="India"))
        for _ in range(10):
            players.append(cls.generate_player(tier="star"))

        # Generate good players
        for _ in range(15):
            players.append(cls.generate_player(tier="good", nationality="India"))
        for _ in range(20):
            players.append(cls.generate_player(tier="good"))

        # Generate average players
        for _ in range(40):
            players.append(cls.generate_player(tier="average", nationality="India"))
        for _ in range(20):
            players.append(cls.generate_player(tier="average"))

        # Generate developing players (mostly Indian)
        for _ in range(35):
            players.append(cls.generate_player(tier="developing", nationality="India"))
        for _ in range(5):
            players.append(cls.generate_player(tier="developing"))

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
