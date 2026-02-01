import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Use /app/data in Docker, current dir otherwise
db_path = os.environ.get("DATABASE_PATH", "willow_leather.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """Create all tables"""
    from app.models import user, player, team, match, playing_xi, career, auction  # noqa
    Base.metadata.create_all(bind=engine)


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
