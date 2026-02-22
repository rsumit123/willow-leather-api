"""
Team Generator - Creates fictional franchise teams for all tiers.
"""
import random
from app.models.team import Team
from app.database import get_session


# ─── District-level teams (6 teams, small-town feel) ────────────────

DISTRICT_TEAMS = [
    {
        "name": "Jamshedpur Tigers",
        "short_name": "JT",
        "city": "Jamshedpur",
        "home_ground": "Keenan Stadium",
        "primary_color": "#D97706",
        "secondary_color": "#1F2937",
        "budget": 0,
    },
    {
        "name": "Ranchi Rockets",
        "short_name": "RR",
        "city": "Ranchi",
        "home_ground": "JSCA Oval",
        "primary_color": "#DC2626",
        "secondary_color": "#FFFFFF",
        "budget": 0,
    },
    {
        "name": "Bokaro Blasters",
        "short_name": "BB",
        "city": "Bokaro",
        "home_ground": "City Park Ground",
        "primary_color": "#2563EB",
        "secondary_color": "#F59E0B",
        "budget": 0,
    },
    {
        "name": "Dhanbad Dynamos",
        "short_name": "DD",
        "city": "Dhanbad",
        "home_ground": "Coal India Ground",
        "primary_color": "#059669",
        "secondary_color": "#000000",
        "budget": 0,
    },
    {
        "name": "Hazaribagh Hawks",
        "short_name": "HH",
        "city": "Hazaribagh",
        "home_ground": "Municipal Ground",
        "primary_color": "#7C3AED",
        "secondary_color": "#E5E7EB",
        "budget": 0,
    },
    {
        "name": "Deoghar Devils",
        "short_name": "DV",
        "city": "Deoghar",
        "home_ground": "Deoghar Sports Complex",
        "primary_color": "#BE185D",
        "secondary_color": "#1E3A5F",
        "budget": 0,
    },
]


# ─── State-level teams (8 teams, Ranji Trophy / state T20 feel) ────

STATE_TEAMS = [
    {
        "name": "Bengal Royals",
        "short_name": "BR",
        "city": "Kolkata",
        "home_ground": "Eden Gardens",
        "primary_color": "#7C3AED",
        "secondary_color": "#FBBF24",
        "budget": 300000000,
    },
    {
        "name": "Maharashtra Warriors",
        "short_name": "MW",
        "city": "Pune",
        "home_ground": "MCA Stadium",
        "primary_color": "#EA580C",
        "secondary_color": "#1E3A5F",
        "budget": 300000000,
    },
    {
        "name": "Karnataka Lions",
        "short_name": "KL",
        "city": "Bangalore",
        "home_ground": "M. Chinnaswamy Stadium",
        "primary_color": "#DC2626",
        "secondary_color": "#000000",
        "budget": 300000000,
    },
    {
        "name": "Tamil Nadu Kings",
        "short_name": "TK",
        "city": "Chennai",
        "home_ground": "M.A. Chidambaram Stadium",
        "primary_color": "#FBBF24",
        "secondary_color": "#1E40AF",
        "budget": 300000000,
    },
    {
        "name": "Delhi Dashers",
        "short_name": "DD",
        "city": "Delhi",
        "home_ground": "Arun Jaitley Stadium",
        "primary_color": "#2563EB",
        "secondary_color": "#DC2626",
        "budget": 300000000,
    },
    {
        "name": "Gujarat Gladiators",
        "short_name": "GG",
        "city": "Ahmedabad",
        "home_ground": "Narendra Modi Stadium",
        "primary_color": "#0891B2",
        "secondary_color": "#F97316",
        "budget": 300000000,
    },
    {
        "name": "Rajasthan Rangers",
        "short_name": "RJ",
        "city": "Jaipur",
        "home_ground": "Sawai Mansingh Stadium",
        "primary_color": "#DB2777",
        "secondary_color": "#1E3A5F",
        "budget": 300000000,
    },
    {
        "name": "Punjab Panthers",
        "short_name": "PP",
        "city": "Mohali",
        "home_ground": "PCA Stadium",
        "primary_color": "#B91C1C",
        "secondary_color": "#9CA3AF",
        "budget": 300000000,
    },
]


# ─── IPL-level teams (8 teams, franchise feel) ─────────────────────

# 8 Fictional IPL-style teams
FRANCHISE_TEAMS = [
    {
        "name": "Mumbai Titans",
        "short_name": "MT",
        "city": "Mumbai",
        "home_ground": "Wankhede Stadium",
        "primary_color": "#004BA0",
        "secondary_color": "#FFD700",
        "budget": 900000000,  # 90 crore
    },
    {
        "name": "Chennai Kings",
        "short_name": "CK",
        "city": "Chennai",
        "home_ground": "M.A. Chidambaram Stadium",
        "primary_color": "#FFFF00",
        "secondary_color": "#0000FF",
        "budget": 900000000,
    },
    {
        "name": "Bangalore Warriors",
        "short_name": "BW",
        "city": "Bangalore",
        "home_ground": "M. Chinnaswamy Stadium",
        "primary_color": "#EC1C24",
        "secondary_color": "#000000",
        "budget": 900000000,
    },
    {
        "name": "Kolkata Knights",
        "short_name": "KK",
        "city": "Kolkata",
        "home_ground": "Eden Gardens",
        "primary_color": "#3A225D",
        "secondary_color": "#FFD700",
        "budget": 900000000,
    },
    {
        "name": "Delhi Capitals",
        "short_name": "DC",
        "city": "Delhi",
        "home_ground": "Arun Jaitley Stadium",
        "primary_color": "#0078BC",
        "secondary_color": "#EF1B23",
        "budget": 900000000,
    },
    {
        "name": "Hyderabad Sunrisers",
        "short_name": "HS",
        "city": "Hyderabad",
        "home_ground": "Rajiv Gandhi Intl. Stadium",
        "primary_color": "#FF822A",
        "secondary_color": "#000000",
        "budget": 900000000,
    },
    {
        "name": "Rajasthan Royals",
        "short_name": "RR",
        "city": "Jaipur",
        "home_ground": "Sawai Mansingh Stadium",
        "primary_color": "#EA1A85",
        "secondary_color": "#254AA5",
        "budget": 900000000,
    },
    {
        "name": "Punjab Lions",
        "short_name": "PL",
        "city": "Mohali",
        "home_ground": "PCA Stadium",
        "primary_color": "#ED1B24",
        "secondary_color": "#A7A9AC",
        "budget": 900000000,
    },
]


TIER_TEAM_MAP = {
    "district": DISTRICT_TEAMS,
    "state": STATE_TEAMS,
    "ipl": FRANCHISE_TEAMS,
}


class TeamGenerator:
    """Generates franchise teams for any tier"""

    @classmethod
    def create_teams(cls, career_id: int, user_team_index: int = 0, tier: str = "ipl") -> list[Team]:
        """
        Create teams for a career.

        Args:
            career_id: ID of the career these teams belong to
            user_team_index: Index of the team the user manages.
                For district (-1 or None = random assignment).
            tier: "district", "state", or "ipl"

        Returns:
            List of Team objects (not yet saved to DB)
        """
        team_list = TIER_TEAM_MAP.get(tier, FRANCHISE_TEAMS)

        if user_team_index is None or user_team_index < 0:
            user_team_index = random.randint(0, len(team_list) - 1)

        teams = []
        for i, team_data in enumerate(team_list):
            team = Team(
                career_id=career_id,
                name=team_data["name"],
                short_name=team_data["short_name"],
                city=team_data["city"],
                home_ground=team_data["home_ground"],
                primary_color=team_data["primary_color"],
                secondary_color=team_data["secondary_color"],
                budget=team_data["budget"],
                remaining_budget=team_data["budget"],
                is_user_team=(i == user_team_index),
            )
            teams.append(team)
        return teams

    @classmethod
    def save_teams_to_db(cls, teams: list[Team]) -> list[Team]:
        """Save teams to database and return with IDs"""
        session = get_session()
        try:
            for team in teams:
                session.add(team)
            session.commit()
            for team in teams:
                session.refresh(team)
            return teams
        finally:
            session.close()

    @classmethod
    def get_team_choices(cls, tier: str = "ipl") -> list[dict]:
        """Get list of teams for user selection"""
        team_list = TIER_TEAM_MAP.get(tier, FRANCHISE_TEAMS)
        return [
            {
                "index": i,
                "name": t["name"],
                "short_name": t["short_name"],
                "city": t["city"],
            }
            for i, t in enumerate(team_list)
        ]
