"""
Authentication API routes for MaterialHub.
Handles login, logout, and session validation.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from typing import Optional

from database import get_session, User
from auth import verify_password, create_session, delete_session, validate_session


router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict
    expires_at: str


class LogoutResponse(BaseModel):
    success: bool


class CheckResponse(BaseModel):
    valid: bool
    user: dict = None


def get_db():
    """Dependency to get database session."""
    with get_session() as session:
        yield session


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: DBSession = Depends(get_db)):
    """
    Authenticate user and create a session token.
    Returns token, user info, and expiration time.
    """
    # Find user by username
    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create session
    session_token = create_session(db, user.id)

    return LoginResponse(
        token=session_token.token,
        user=user.to_dict(),
        expires_at=session_token.expires_at.isoformat()
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(authorization: Optional[str] = Header(None), db: DBSession = Depends(get_db)):
    """
    Logout user by deleting their session token.
    Requires Authorization header with Bearer token.
    """
    # Extract token from Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")

    # Delete session
    deleted = delete_session(db, token)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return LogoutResponse(success=True)


@router.get("/check", response_model=CheckResponse)
def check(authorization: Optional[str] = Header(None), db: DBSession = Depends(get_db)):
    """
    Check if a session token is valid.
    Requires Authorization header with Bearer token.
    """
    # Extract token from Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        return CheckResponse(valid=False)

    token = authorization.replace("Bearer ", "")

    # Validate session
    user = validate_session(db, token)

    if not user:
        return CheckResponse(valid=False)

    return CheckResponse(valid=True, user=user.to_dict())
