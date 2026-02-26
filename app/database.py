import os
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Use /app/data in Docker, current dir otherwise
db_path = os.environ.get("DATABASE_PATH", "willow_leather.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """Create all tables and run column migrations."""
    from app.models import user, player, team, match, playing_xi, career, auction  # noqa
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Add missing columns to existing tables (SQLite doesn't support full ALTER)."""
    migrations = [
        ("careers", "tier", 'VARCHAR(20) DEFAULT "ipl"'),
        ("careers", "reputation", "INTEGER DEFAULT 0"),
        ("careers", "trophies_won", "INTEGER DEFAULT 0"),
        ("careers", "seasons_played", "INTEGER DEFAULT 0"),
        ("careers", "promoted_at_season", "INTEGER"),
        ("careers", "game_over", "BOOLEAN DEFAULT 0"),
        ("careers", "game_over_reason", "VARCHAR(50)"),
        ("fixtures", "scheduled_date", "VARCHAR(10)"),
        ("fixtures", "pitch_name", "VARCHAR(30)"),
    ]
    inspector = inspect(engine)
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                existing = [c["name"] for c in inspector.get_columns(table)]
            except Exception:
                continue  # Table doesn't exist yet
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.commit()


def get_session():
    """Get a database session - for direct use (caller must close)"""
    return SessionLocal()


def get_db():
    """FastAPI dependency - yields session and closes after request"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
