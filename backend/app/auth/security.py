"""
Mock SSO for demo purposes: real identity providers (SAML/OIDC) issue a token
after authenticating a user against the company directory. Here, we skip the
external IdP and let the demo caller pick a seeded user id directly, then
issue a normal signed JWT exactly like a real SSO integration would hand us.

This keeps everything downstream of login (permission filtering, retrieval)
identical to how it would work with a real IdP -- swapping in real SSO later
only touches this file, not the retrieval/permission logic.
"""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.models import User

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()


def issue_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user
