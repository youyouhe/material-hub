"""
Authentication utilities for MaterialHub.
Handles password hashing, session creation, and token validation.
"""

import os
import uuid
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from database import User, SessionToken


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


def create_session(db: Session, user_id: int) -> SessionToken:
    """Create a new session token for a user."""
    session_hours = int(os.getenv("AUTH_SESSION_HOURS", "24"))
    token = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(hours=session_hours)

    session_token = SessionToken(
        user_id=user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=expires_at
    )

    db.add(session_token)
    db.commit()
    db.refresh(session_token)

    return session_token


def validate_session(db: Session, token: str) -> Optional[User]:
    """
    Validate a session token and return the associated user if valid.
    Returns None if token is invalid or expired.
    """
    session_token = db.query(SessionToken).filter(SessionToken.token == token).first()

    if not session_token:
        return None

    # Check if token is expired
    if session_token.expires_at < datetime.utcnow():
        # Clean up expired session
        db.delete(session_token)
        db.commit()
        return None

    # Update user's last login
    user = session_token.user
    user.last_login = datetime.utcnow()
    db.commit()

    return user


def delete_session(db: Session, token: str) -> bool:
    """Delete a session token (logout). Returns True if deleted, False if not found."""
    session_token = db.query(SessionToken).filter(SessionToken.token == token).first()

    if not session_token:
        return False

    db.delete(session_token)
    db.commit()
    return True


def cleanup_expired_sessions(db: Session) -> int:
    """Clean up all expired sessions. Returns count of deleted sessions."""
    now = datetime.utcnow()
    expired_sessions = db.query(SessionToken).filter(SessionToken.expires_at < now).all()

    count = len(expired_sessions)
    for session in expired_sessions:
        db.delete(session)

    db.commit()
    return count
