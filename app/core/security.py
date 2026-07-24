import os
import uuid
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Union

from jose import JWTError, jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Database and Model imports for the dependency
from app.db.session import get_db
from app.domains.users.models import User

# ── Configuration ─────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 

# This tells FastAPI where to look for the login token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class TokenData(BaseModel):
    sub: Optional[str] = None

# ── Password Logic (Native Bcrypt) ────────────────────────────

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored hash using native bcrypt."""
    plain_bytes = plain_password.encode('utf-8')
    if len(plain_bytes) > 72:
        plain_bytes = plain_bytes[:72]
        
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hash_bytes)

def get_password_hash(password: str) -> str:
    """Securely hashes a password using native bcrypt with a strict 72-byte limit."""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
        
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

# ── Token Logic ───────────────────────────────────────────────

def create_access_token(subject: Union[str, any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise JWTError("Token missing subject")
        return TokenData(sub=user_id)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ── The Missing Dependency ────────────────────────────────────

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Extracts user from JWT and provides it to route functions.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token_data = decode_access_token(token)
        if token_data.sub is None:
            raise credentials_exception
        user_id = token_data.sub
    except Exception:
        raise credentials_exception

    # Safety net: Catch malformed token strings before they crash the UUID parser
    try:
        parsed_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception

    # Query the DB to find the user attached to this token
    result = await db.execute(select(User).where(User.id == parsed_uuid))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
        
    return user