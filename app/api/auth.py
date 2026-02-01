"""
Authentication API routes
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.database import get_session
from app.models.user import User
from app.auth.config import settings
from app.auth.utils import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# Request/Response schemas
class GoogleAuthRequest(BaseModel):
    token: str  # Google ID token from frontend


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/google", response_model=AuthResponse)
def google_auth(
    request: GoogleAuthRequest,
    db: Session = Depends(get_session),
):
    """
    Authenticate with Google OAuth.
    Verifies the Google ID token and creates/returns a user with JWT tokens.
    """
    try:
        # Verify the Google token
        idinfo = id_token.verify_oauth2_token(
            request.token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )

        # Extract user info from Google token
        google_id = idinfo["sub"]
        email = idinfo["email"]
        name = idinfo.get("name", email.split("@")[0])
        picture = idinfo.get("picture")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}",
        )

    # Find or create user
    user = db.query(User).filter(User.google_id == google_id).first()

    if user is None:
        # Create new user
        user = User(
            email=email,
            google_id=google_id,
            name=name,
            avatar_url=picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update existing user info (name/avatar might change)
        user.name = name
        user.avatar_url = picture
        db.commit()

    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: RefreshRequest,
    db: Session = Depends(get_session),
):
    """
    Refresh an access token using a valid refresh token.
    """
    user_id = verify_token(request.refresh_token, "refresh")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Verify user still exists
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Generate new access token
    access_token = create_access_token(user.id)

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the current authenticated user's info.
    """
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """
    Logout endpoint.
    Note: JWT tokens are stateless, so this is mainly for client-side cleanup.
    In production, you might want to implement a token blacklist.
    """
    return {"message": "Logged out successfully"}
