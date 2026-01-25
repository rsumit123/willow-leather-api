from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///willow_leather.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """Create all tables"""
    from app.models import player, team, match  # noqa
    Base.metadata.create_all(bind=engine)


def get_session():
    """Get a database session"""
    return SessionLocal()
