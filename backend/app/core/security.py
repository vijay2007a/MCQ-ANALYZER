import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
import bcrypt
import jwt
from app.core.config import settings

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _ph = PasswordHasher()
    _HAS_ARGON2 = True
except ImportError:
    _ph = None
    _HAS_ARGON2 = False


def hash_password(password: str) -> str:
    """
    Securely hash password using Argon2id if available, otherwise bcrypt.
    """
    if _HAS_ARGON2 and _ph:
        return _ph.hash(password)
    else:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password hash safely in constant time. Supports both Argon2 and Bcrypt.
    """
    if not hashed_password or not plain_password:
        return False

    if hashed_password.startswith("$argon2"):
        if _HAS_ARGON2 and _ph:
            try:
                return _ph.verify(hashed_password, plain_password)
            except VerifyMismatchError:
                return False
            except Exception:
                return False
        return False
    elif hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$") or hashed_password.startswith("$2y$"):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False
    return False


def create_access_token(
    subject: Union[str, Any],
    role: str = "ADMIN",
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create signed JWT access token for admin authentication.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode: Dict[str, Any] = {
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "sub": str(subject),
        "role": role,
        "type": "access",
        "admin_auth_version": 2,
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def generate_player_session_token() -> str:
    """
    Generate cryptographically secure high-entropy random player session token.
    """
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """
    Hash player session token using SHA-256 before storing in database.
    Prevents token leakage in database dumps.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
