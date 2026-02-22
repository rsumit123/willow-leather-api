"""
Tier configuration constants for District, State, and IPL levels.
"""

TIER_CONFIG = {
    "district": {
        "team_count": 6,
        "squad_size": 15,
        "matches_per_team": 10,       # round-robin once (6C2 = 15 total matches)
        "max_player_rating": 65,
        "has_auction": False,
        "has_transfers": False,
        "playoff_teams": 4,
        "format": "T20",
        "max_overseas": 0,
        "calendar_months": ["jan", "feb", "mar"],
        "pitches": ["muddy", "grassless", "uneven_bounce", "village_green", "balanced"],
        "promotion_condition": "win_trophy",
        "sack_condition": "finish_last_twice",
        "salary_cap": 0,
        "total_league_matches": 30,   # 6 teams, double round-robin: 6C2 * 2 = 30
    },
    "state": {
        "team_count": 8,
        "squad_size": 25,
        "playing_squad": 15,
        "matches_per_team": 14,
        "max_player_rating": 80,
        "has_auction": False,
        "has_transfers": True,
        "playoff_teams": 4,
        "format": "T20",
        "max_overseas": 2,
        "calendar_months": ["apr", "may", "jun", "jul"],
        "pitches": ["green_seamer", "dust_bowl", "flat_deck", "bouncy_track", "slow_turner", "balanced"],
        "promotion_condition": "reach_final",
        "sack_condition": "finish_bottom_half_twice",
        "salary_cap": 300_000_000,
        "total_league_matches": 56,   # 8 teams * 14 / 2
    },
    "ipl": {
        "team_count": 8,
        "squad_size": 25,
        "matches_per_team": 14,
        "max_player_rating": 100,
        "has_auction": True,
        "has_transfers": True,
        "playoff_teams": 4,
        "format": "T20",
        "max_overseas": 8,
        "calendar_months": ["mar", "apr", "may"],
        "pitches": ["green_seamer", "dust_bowl", "flat_deck", "bouncy_track", "slow_turner", "balanced"],
        "promotion_condition": None,
        "sack_condition": "finish_last_three_times",
        "salary_cap": 900_000_000,
        "total_league_matches": 56,
    },
}


# Reputation title thresholds
REPUTATION_TITLES = {
    0: "Unknown",
    20: "Promising",
    40: "Rising Star",
    60: "Established",
    80: "Legend",
}


def get_reputation_title(reputation: int) -> str:
    """Get the title for a given reputation score."""
    title = "Unknown"
    for threshold, name in sorted(REPUTATION_TITLES.items()):
        if reputation >= threshold:
            title = name
    return title


# Drill configurations
DRILL_CONFIG = {
    "nets_batting": {
        "display_name": "Net Practice",
        "description": "+2 Batting for 2 matches",
        "boost_attribute": "batting",
        "boost_amount": 2,
        "duration": 2,
        "best_for": ["batsman", "all_rounder", "wicket_keeper"],
        "min_tier": "district",
        "icon": "bat",
    },
    "bowling_practice": {
        "display_name": "Bowling Practice",
        "description": "+2 Bowling for 2 matches",
        "boost_attribute": "bowling",
        "boost_amount": 2,
        "duration": 2,
        "best_for": ["bowler", "all_rounder"],
        "min_tier": "district",
        "icon": "target",
    },
    "fielding_drills": {
        "display_name": "Fielding Drills",
        "description": "+2 Fielding for 2 matches",
        "boost_attribute": "fielding",
        "boost_amount": 2,
        "duration": 2,
        "best_for": ["batsman", "bowler", "all_rounder", "wicket_keeper"],
        "min_tier": "district",
        "icon": "hand",
    },
    "fitness_camp": {
        "display_name": "Fitness Camp",
        "description": "+2 Fitness for 2 matches",
        "boost_attribute": "fitness",
        "boost_amount": 2,
        "duration": 2,
        "best_for": ["batsman", "bowler", "all_rounder", "wicket_keeper"],
        "min_tier": "district",
        "icon": "heart",
    },
    "spin_workshop": {
        "display_name": "Spin Workshop",
        "description": "+3 vs Spin DNA for 2 matches",
        "boost_attribute": "vs_spin",
        "boost_amount": 3,
        "duration": 2,
        "best_for": ["batsman", "all_rounder", "wicket_keeper"],
        "min_tier": "state",
        "icon": "rotate",
    },
    "pace_handling": {
        "display_name": "Pace Handling",
        "description": "+3 vs Pace DNA for 2 matches",
        "boost_attribute": "vs_pace",
        "boost_amount": 3,
        "duration": 2,
        "best_for": ["batsman", "all_rounder", "wicket_keeper"],
        "min_tier": "state",
        "icon": "zap",
    },
    "power_hitting": {
        "display_name": "Power Hitting",
        "description": "+3 Power DNA for 2 matches",
        "boost_attribute": "power",
        "boost_amount": 3,
        "duration": 2,
        "best_for": ["batsman", "all_rounder"],
        "min_tier": "state",
        "icon": "flame",
    },
    "death_bowling": {
        "display_name": "Death Bowling",
        "description": "+3 Control DNA for 2 matches",
        "boost_attribute": "control",
        "boost_amount": 3,
        "duration": 2,
        "best_for": ["bowler", "all_rounder"],
        "min_tier": "state",
        "icon": "crosshair",
    },
}
