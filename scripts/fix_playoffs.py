"""Fix duplicate playoff fixtures for career 2."""
import sys
sys.path.insert(0, ".")

from app.database import get_session
from app.models.career import Fixture, FixtureType, FixtureStatus

db = get_session()

# Get all fixtures for season 2
fixtures = db.query(Fixture).filter(Fixture.season_id == 2).order_by(Fixture.id).all()
league = [f for f in fixtures if f.fixture_type == FixtureType.LEAGUE]
playoff = [f for f in fixtures if f.fixture_type != FixtureType.LEAGUE]

print(f"League: {len(league)} fixtures")
print(f"Playoff: {len(playoff)} fixtures")

for f in playoff:
    print(f"  id={f.id} type={f.fixture_type.value} match#={f.match_number} status={f.status.value} t1={f.team1_id} t2={f.team2_id} winner={f.winner_id}")

if len(playoff) > 2:
    print(f"\nFound {len(playoff)} playoff fixtures — duplicates detected!")
    # Keep the first Q1 (completed, id=61) and first Eliminator (id=62)
    # Delete all others
    keep_ids = set()
    seen_types = set()
    for f in playoff:
        if f.fixture_type.value not in seen_types:
            keep_ids.add(f.id)
            seen_types.add(f.fixture_type.value)

    to_delete = [f for f in playoff if f.id not in keep_ids]
    print(f"Keeping: {keep_ids}")
    print(f"Deleting: {[f.id for f in to_delete]}")

    for f in to_delete:
        db.delete(f)
    db.commit()
    print("Duplicates removed!")
else:
    print("No duplicates found.")

# Show final state
remaining = db.query(Fixture).filter(Fixture.season_id == 2).filter(
    Fixture.fixture_type != FixtureType.LEAGUE
).order_by(Fixture.id).all()
print(f"\nFinal playoff fixtures:")
for f in remaining:
    print(f"  id={f.id} type={f.fixture_type.value} match#={f.match_number} status={f.status.value} t1={f.team1_id} t2={f.team2_id} winner={f.winner_id}")

db.close()
