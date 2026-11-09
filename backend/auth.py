from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)
# A dummy hash keeps unknown-user login failures on the password verification path.
DUMMY_HASH = bcrypt.hashpw(b'not-a-real-password', bcrypt.gensalt())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    if len(password.encode()) > 72:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {'sub': str(user_id), 'iat': now,
         'exp': now + timedelta(minutes=settings.access_token_expire_minutes)},
        settings.secret_key, algorithm='HS256',
    )


def unauthorized():
    return HTTPException(401, 'Your session is invalid or expired. Please log in again.',
                         headers={'WWW-Authenticate': 'Bearer'})


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key,
                             algorithms=['HS256'], options={'require': ['sub', 'exp', 'iat']})
        user = db.get(User, int(payload['sub']))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized()
    if user is None:
        raise unauthorized()
    return user


def get_current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise unauthorized()
    return user
