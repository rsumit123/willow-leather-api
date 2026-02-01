#!/usr/bin/env python3
"""
Migration script for authentication.
WARNING: This will DELETE ALL existing data and recreate tables.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base


def migrate():
    """Drop all tables and recreate with new schema"""
    # Import all models to register them with Base
    from app.models import user, player, team, match, playing_xi, career, auction  # noqa

    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating tables with new schema...")
    Base.metadata.create_all(bind=engine)
    print("Migration complete!")


if __name__ == "__main__":
    print("=" * 60)
    print("WARNING: This will DELETE ALL existing data!")
    print("=" * 60)
    confirm = input("Type 'yes' to confirm: ")
    if confirm.lower() == 'yes':
        migrate()
    else:
        print("Migration cancelled.")
