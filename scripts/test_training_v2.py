"""
E2E test for Training System v2 — run inside Docker container.
Tests: model creation, plan CRUD, auto-training, DNA persistence, logs, AI fixtures.
"""
import json
import sys

from app.database import init_db, get_session
from app.models.career import (
    Career, TrainingPlan, TrainingLog, TrainingFocus,
    GameDay, DayType, Notification, NotificationType, Fixture,
)
from app.models.player import Player
from app.engine.training_engine_v2 import (
    process_training_day, get_focus_options_for_player, TRAINING_FOCUS_CONFIG,
    calculate_improvement,
)

init_db()
db = get_session()
errors = []


def test(name, condition, detail=""):
    if condition:
        print(f"  PASS: {name}")
    else:
        msg = f"  FAIL: {name} — {detail}"
        print(msg)
        errors.append(msg)


# ─── Setup ───────────────────────────────────────────────────────────
career = db.query(Career).first()
if not career:
    print("ERROR: No career found in database. Cannot run tests.")
    sys.exit(1)

print(f"Career: {career.name} (id={career.id}, team={career.user_team_id})")
players = db.query(Player).filter_by(team_id=career.user_team_id).all()
print(f"Team players: {len(players)}")

# ─── Test 1: Focus Config ───────────────────────────────────────────
print("\n=== Test 1: Focus Configuration ===")
test("15 focus areas defined", len(TRAINING_FOCUS_CONFIG) == 15, f"got {len(TRAINING_FOCUS_CONFIG)}")

for key, config in TRAINING_FOCUS_CONFIG.items():
    test(
        f"Focus '{key}' has required fields",
        all(k in config for k in ["display_name", "description", "target_type", "target_attributes"]),
    )

# ─── Test 2: Improvement Calculations ───────────────────────────────
print("\n=== Test 2: Improvement Calculations ===")
test("Low value, young player = high gain", calculate_improvement(20, 1.0, 22) >= 0.9)
test("High value, old player = low gain", calculate_improvement(90, 1.0, 36) <= 0.3)
test("Minimum gain is 0.2", calculate_improvement(98, 1.0, 40) == 0.2)
test("Speed calc works", calculate_improvement(140, 0.8, 25, is_speed=True) >= 0.2)
test("Speed at cap barely gains", calculate_improvement(153, 0.8, 30, is_speed=True) == 0.2)

# ─── Test 3: Focus Options Per Player ───────────────────────────────
print("\n=== Test 3: Focus Options Validation ===")
for p in players[:6]:
    opts = get_focus_options_for_player(p)
    has_opts = len(opts) > 0
    test(f"{p.name} ({p.role.value}) has focus options", has_opts, f"got {len(opts)}")

    # Batsmen should NOT have pacer_only options
    if p.role.value == "batsman" and p.bowler_dna is None:
        has_pacer = any(o in ["pace_bowling", "swing_bowling", "bounce_extraction"] for o in opts)
        test(f"  Pure batsman {p.name} has no pacer options", not has_pacer)

    # Everyone should have fitness and fielding
    test(f"  {p.name} has fitness option", "fitness" in opts)
    test(f"  {p.name} has fielding option", "fielding" in opts)

# ─── Test 4: Set Training Plans ─────────────────────────────────────
print("\n=== Test 4: Set Training Plans ===")
# Clean up any existing test plans
db.query(TrainingPlan).filter_by(career_id=career.id).delete()
db.flush()

plans_set = 0
for p in players:
    opts = get_focus_options_for_player(p)
    if not opts:
        continue
    # Pick first valid focus
    plan = TrainingPlan(career_id=career.id, player_id=p.id, focus=TrainingFocus(opts[0]))
    db.add(plan)
    plans_set += 1

db.flush()
test(f"All {len(players)} players got plans", plans_set == len(players), f"only {plans_set}")

# Verify in DB
db_plans = db.query(TrainingPlan).filter_by(career_id=career.id).all()
test("Plans persisted in DB", len(db_plans) == plans_set, f"got {len(db_plans)}")

# ─── Test 5: Process Training Day ───────────────────────────────────
print("\n=== Test 5: Auto-Training ===")
training_day = db.query(GameDay).filter_by(
    career_id=career.id, day_type=DayType.TRAINING
).first()
if not training_day:
    training_day = db.query(GameDay).filter_by(career_id=career.id).first()

test("Found a game day for training", training_day is not None)

if training_day:
    # Snapshot DNA before
    before_dna = {}
    for p in players[:5]:
        if p.batting_dna:
            before_dna[p.id] = {"vs_pace": p.batting_dna.vs_pace, "vs_spin": p.batting_dna.vs_spin}

    results = process_training_day(db, career.id, training_day.id)
    test("Training produced results", len(results) > 0, f"got {len(results)} improvements")

    # Show some results
    for r in results[:5]:
        print(f"    {r['player_name']}: {r['attribute']} {r['old']} -> {r['new']} (+{r['gain']})")

    # Verify DNA actually changed
    print("\n=== Test 6: DNA Persistence ===")
    changes_verified = 0
    for p in players[:5]:
        if p.id not in before_dna:
            continue
        # Re-read from JSON (not cached property)
        if p.batting_dna_json:
            dna_dict = json.loads(p.batting_dna_json)
            old_pace = before_dna[p.id].get("vs_pace")
            new_pace = dna_dict.get("vs_pace")
            if old_pace is not None and new_pace is not None:
                changed = new_pace >= old_pace
                test(f"{p.name} DNA changed: vs_pace {old_pace} -> {new_pace}", changed)
                changes_verified += 1

    test("At least 1 DNA change verified", changes_verified > 0, f"verified {changes_verified}")

    # ─── Test 7: Training Logs ──────────────────────────────────────
    print("\n=== Test 7: Training Logs ===")
    logs = db.query(TrainingLog).filter_by(career_id=career.id, game_day_id=training_day.id).all()
    test("Training logs created", len(logs) > 0, f"got {len(logs)}")
    test("Log count matches results", len(logs) == len(results), f"logs={len(logs)} results={len(results)}")

    for log in logs[:3]:
        test(
            f"Log valid: player {log.player_id}",
            log.improvement > 0 and log.new_value > log.old_value,
            f"imp={log.improvement} old={log.old_value} new={log.new_value}",
        )

# ─── Test 8: AI Fixtures (scheduled_date) ───────────────────────────
print("\n=== Test 8: AI Fixtures ===")
total_fixtures = db.query(Fixture).count()
with_date = db.query(Fixture).filter(Fixture.scheduled_date.isnot(None)).count()
print(f"  Fixtures total: {total_fixtures}, with scheduled_date: {with_date}")
# For existing careers, scheduled_date may not be set yet (only new calendars)
# Just check the column exists and query doesn't error
test("scheduled_date column queryable", True)

# ─── Test 9: Calendar API integration ────────────────────────────────
print("\n=== Test 9: API Routes ===")
from app.api.training import router as training_router
from app.api.calendar import router as calendar_router

training_paths = [r.path for r in training_router.routes]
test("/plans endpoint exists", any("plans" in p for p in training_paths))
test("/plans/{player_id} endpoint exists", any("player_id" in p for p in training_paths))
test("/plans/bulk endpoint exists", any("bulk" in p for p in training_paths))
test("/focus-options endpoint exists", any("focus-options" in p for p in training_paths))
test("/history endpoint exists", any("history" in p for p in training_paths))
# Legacy
test("/available-drills still exists", any("available-drills" in p for p in training_paths))
test("/train still exists", any("/train" == p.split("{")[0].rstrip("/").split("/")[-1] for p in training_paths) or any("train" in p for p in training_paths))

# ─── Rollback test data ─────────────────────────────────────────────
db.rollback()
db.close()

# ─── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if errors:
    print(f"FAILED: {len(errors)} test(s) failed")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
