from app.models.player import PlayerRole


class PlayingXIValidator:
    @staticmethod
    def validate(players: list) -> dict:
        """
        Validate a playing XI selection.

        Rules:
        1. Exactly 11 players
        2. At least 1 wicket keeper
        3. Minimum bowling options: 4 bowlers + 1 all-rounder OR 5 bowlers
        4. Max 4 overseas players
        """
        errors = []

        if len(players) != 11:
            errors.append(f"Must select exactly 11 players, got {len(players)}")

        wk_count = sum(1 for p in players if p.role == PlayerRole.WICKET_KEEPER)
        if wk_count == 0:
            errors.append("Must include at least 1 wicket keeper")

        overseas_count = sum(1 for p in players if p.is_overseas)
        if overseas_count > 4:
            errors.append(f"Max 4 overseas players allowed, got {overseas_count}")

        bowler_count = sum(1 for p in players if p.role == PlayerRole.BOWLER)
        ar_count = sum(1 for p in players if p.role == PlayerRole.ALL_ROUNDER)

        if not (bowler_count >= 5 or (bowler_count >= 4 and ar_count >= 1)):
            errors.append(f"Need 5 bowlers OR 4 bowlers + 1 all-rounder. Got {bowler_count} bowlers, {ar_count} all-rounders")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "breakdown": {
                "batsmen": sum(1 for p in players if p.role == PlayerRole.BATSMAN),
                "bowlers": bowler_count,
                "all_rounders": ar_count,
                "wicket_keepers": wk_count,
                "overseas": overseas_count
            }
        }
