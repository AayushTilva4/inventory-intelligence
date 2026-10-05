import os
import hashlib
import jwt
import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text
from app.db.connection import get_poc_engine

router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer()

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-poc-key")
JWT_ALGORITHM = "HS256"

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    salt = b'some-fixed-salt-for-poc'
    hashed = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1, maxmem=0)
    return hashed.hex()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

@router.post("/signup")
def signup(req: SignupRequest):
    engine = get_poc_engine()
    with engine.begin() as conn:
        check = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": req.email}).first()
        if check:
            raise HTTPException(status_code=400, detail="Email already registered")

        pw_hash = hash_password(req.password)
        conn.execute(
            text("INSERT INTO users (name, email, password_hash) VALUES (:name, :email, :hash)"),
            {"name": req.name, "email": req.email, "hash": pw_hash}
        )
    return {"message": "User created successfully"}

@router.post("/login")
def login(req: LoginRequest):
    engine = get_poc_engine()
    with engine.begin() as conn:
        user = conn.execute(text("SELECT id, name, email, password_hash FROM users WHERE email = :email"), {"email": req.email}).first()
        if not user or not verify_password(req.password, user[3]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = jwt.encode(
            {"sub": str(user[0]), "name": user[1], "email": user[2], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )
        return {"token": token, "user": {"id": user[0], "name": user[1], "email": user[2]}}

@router.get("/me")
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"id": payload.get("sub"), "name": payload.get("name"), "email": payload.get("email")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/logout")
def logout():
    return {"message": "Logged out successfully"}
