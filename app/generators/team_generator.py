"""
Team Generator - Creates 8 fictional IPL-style franchise teams
"""
from app.models.team import Team
from app.database import get_session


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


class TeamGenerator:
    """Generates the 8 franchise teams for a career"""

    @classmethod
    def create_teams(cls, career_id: int, user_team_index: int = 0) -> list[Team]:
        """
        Create all 8 franchise teams for a career.

        Args:
            career_id: ID of the career these teams belong to
            user_team_index: Index (0-7) of the team the user wants to manage

        Returns:
            List of Team objects (not yet saved to DB)
        """
        teams = []
        for i, team_data in enumerate(FRANCHISE_TEAMS):
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
            # Refresh to get IDs
            for team in teams:
                session.refresh(team)
            return teams
        finally:
            session.close()

    @classmethod
    def get_team_choices(cls) -> list[dict]:
        """Get list of teams for user selection"""
        return [
            {
                "index": i,
                "name": t["name"],
                "short_name": t["short_name"],
                "city": t["city"],
            }
            for i, t in enumerate(FRANCHISE_TEAMS)
        ]
