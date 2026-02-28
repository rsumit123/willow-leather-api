"""Check playoff state for career 2."""
import sys
sys.path.insert(0, ".")

from app.database import get_session
from app.models.career import Fixture, FixtureType, FixtureStatus, Season, Career
from app.models.team import Team

db = get_session()
career = db.query(Career).get(2)
print(f"Career: status={career.status.value}, tier={career.tier}, user_team={career.user_team_id}")

user_team = db.query(Team).get(career.user_team_id)
print(f"User team: {user_team.short_name} (id={user_team.id})")

season = db.query(Season).filter_by(career_id=2, season_number=career.current_season_number).first()
print(f"Season: phase={season.phase.value}")

fixtures = db.query(Fixture).filter(Fixture.season_id == season.id).order_by(Fixture.id).all()
playoff = [f for f in fixtures if f.fixture_type != FixtureType.LEAGUE]

print(f"\nPlayoff fixtures ({len(playoff)}):")
for f in playoff:
    t1_name = f.team1.short_name if f.team1 else "TBD"
    t2_name = f.team2.short_name if f.team2 else "TBD"
    w_name = ""
    if f.winner_id:
        w = db.query(Team).get(f.winner_id)
        w_name = w.short_name if w else "?"
    print(f"  id={f.id} type={f.fixture_type.value} status={f.status.value} {t1_name} vs {t2_name} winner={w_name} result={f.result_summary}")

# Check what generate_next_playoff would do
from app.engine.season_engine import SeasonEngine
engine = SeasonEngine(db, season)
next_fix = engine.get_next_fixture()
if next_fix:
    print(f"\nNext fixture to simulate: id={next_fix.id} type={next_fix.fixture_type.value} status={next_fix.status.value}")
else:
    print("\nNo next fixture found")

db.close()
