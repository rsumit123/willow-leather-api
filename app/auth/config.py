"""
Authentication configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()


class AuthSettings:
    """Authentication settings from environment variables"""

    # JWT settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 days

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", os.getenv("OAUTH2_CLIENT_ID", ""))

    # Career limit per user
    MAX_CAREERS_PER_USER: int = 3


settings = AuthSettings()
