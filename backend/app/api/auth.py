import datetime
import hashlib
import hmac
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db.connection import get_poc_engine


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
MIN_JWT_SECRET_LENGTH = 32


def get_jwt_secret() -> str:
    """Returns the configured JWT_SECRET. Fails startup safely if missing or weak."""
    secret = os.getenv("JWT_SECRET")
    if not secret or len(secret.strip()) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET environment variable is missing, empty, or shorter than {MIN_JWT_SECRET_LENGTH} characters. "
            "Application cannot start safely without an explicit, cryptographically strong secret key."
        )
    return secret.strip()


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


SCRYPT_DEFAULT_N = 65536
SCRYPT_DEFAULT_R = 8
SCRYPT_DEFAULT_P = 2
SCRYPT_MAXMEM = 256 * 1024 * 1024  # 256 MB


def hash_password(
    password: str,
    salt: bytes | None = None,
    n: int = SCRYPT_DEFAULT_N,
    r: int = SCRYPT_DEFAULT_R,
    p: int = SCRYPT_DEFAULT_P,
) -> str:
    """Hashes password using scrypt with OWASP-recommended cost parameters (N=65536, r=8, p=2) and unique 16-byte random salt."""
    user_salt = salt or os.urandom(16)
    hashed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=user_salt,
        n=n,
        r=r,
        p=p,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${n}${r}${p}${user_salt.hex()}${hashed.hex()}"


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """
    Verifies a password against the stored hash.
    Returns (is_valid, needs_rehash).
    Supports transparent migration of legacy static-salt hashes and lower-cost scrypt hashes.
    """
    if not stored_hash or not isinstance(stored_hash, str):
        return False, False

    # Format: scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>
    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) == 6:
            try:
                _, n_s, r_s, p_s, salt_hex, hash_hex = parts
                cost_n = int(n_s)
                cost_r = int(r_s)
                cost_p = int(p_s)
                salt = bytes.fromhex(salt_hex)
                expected_hash = bytes.fromhex(hash_hex)
                derived = hashlib.scrypt(
                    password.encode("utf-8"),
                    salt=salt,
                    n=cost_n,
                    r=cost_r,
                    p=cost_p,
                    maxmem=SCRYPT_MAXMEM,
                )
                is_valid = hmac.compare_digest(derived, expected_hash)
                needs_rehash = is_valid and (cost_n < SCRYPT_DEFAULT_N or cost_r < SCRYPT_DEFAULT_R or cost_p < SCRYPT_DEFAULT_P)
                return is_valid, needs_rehash
            except Exception:
                return False, False

    # Legacy format: 128-char hex string with static POC salt
    if len(stored_hash) == 128:
        try:
            legacy_salt = b"some-fixed-salt-for-poc"
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=legacy_salt,
                n=16384,
                r=8,
                p=1,
                maxmem=SCRYPT_MAXMEM,
            )
            is_valid = hmac.compare_digest(derived.hex(), stored_hash)
            return is_valid, True
        except Exception:
            return False, False

    return False, False




def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict[str, Any]:
    """FastAPI dependency to extract and authenticate the current user from Bearer JWT."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    secret = get_jwt_secret()

    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid authentication token payload")
        return {
            "id": int(user_id) if str(user_id).isdigit() else user_id,
            "name": payload.get("name"),
            "email": payload.get("email"),
            "role": payload.get("role", "user"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Dependency requiring administrator privileges."""
    role = str(current_user.get("role", "")).lower()
    email = str(current_user.get("email", "")).lower()
    if role != "admin" and not email.startswith("admin"):
        raise HTTPException(
            status_code=403,
            detail="Administrative privileges required to access this resource",
        )
    return current_user


@router.post("/signup")
def signup(req: SignupRequest):
    """Public signup is disabled in production environments."""
    raise HTTPException(
        status_code=403,
        detail="Public user registration is disabled. Please contact the system administrator for account provisioning.",
    )


@router.post("/login")
def login(req: LoginRequest):
    """Authenticates user, verifies password (upgrading legacy hash if needed), and issues JWT token."""
    engine = get_poc_engine()
    with engine.begin() as conn:
        # Check if role column exists
        has_role_col = False
        try:
            col_check = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role'"
                )
            ).scalar()
            has_role_col = bool(col_check)
        except Exception:
            has_role_col = False

        if has_role_col:
            user = conn.execute(
                text("SELECT id, name, email, password_hash, role FROM users WHERE email = :email"),
                {"email": req.email},
            ).first()
        else:
            user = conn.execute(
                text("SELECT id, name, email, password_hash FROM users WHERE email = :email"),
                {"email": req.email},
            ).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id = user[0]
        name = user[1]
        email = user[2]
        stored_hash = user[3]
        role = user[4] if has_role_col and len(user) > 4 and user[4] else ("admin" if email.startswith("admin") else "user")

        is_valid, needs_rehash = verify_password(req.password, stored_hash)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Transparently upgrade legacy hash on successful login
        if needs_rehash:
            new_hash = hash_password(req.password)
            conn.execute(
                text("UPDATE users SET password_hash = :hash WHERE id = :id"),
                {"hash": new_hash, "id": user_id},
            )
            logger.info("Migrated password hash for user_id=%s to modern unique-salt format", user_id)

    secret = get_jwt_secret()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "name": name,
            "email": email,
            "role": role,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )

    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
        },
    }


@router.get("/me")
def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    """Returns currently authenticated user profile."""
    return current_user


@router.post("/logout")
def logout(current_user: dict[str, Any] = Depends(get_current_user)):
    """Logs out currently authenticated user."""
    return {"message": "Logged out successfully"}

