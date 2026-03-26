import random
import uuid
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.core.security import verify_password, create_access_token, get_password_hash, decode_access_token
from app.core.redis import redis_client

# Import models and new schemas
from app.domains.users.models import User
from app.domains.wallet.models import Wallet
from app.domains.users import schemas

router = APIRouter(tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/login", response_model=schemas.LoginResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    """Authenticates the user and returns a strict JWT."""
    safe_email = form_data.username.lower().strip()
    
    query = select(User).where(User.email == safe_email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role
    }

@router.post("/register")
async def register_user(request: schemas.RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Creates a new user and automatically provisions a USD wallet."""
    safe_email = request.email.lower().strip()
    
    query = select(User).where(User.email == safe_email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=safe_email,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role="user"
    )
    db.add(new_user)
    await db.flush() 
    
    new_wallet = Wallet(user_id=new_user.id, currency="USD", cached_balance=0.0)
    db.add(new_wallet)
    
    await db.commit()
    return {"status": "success", "message": "User registered successfully"}

@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_profile(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
):
    """Returns the profile of the currently logged-in user, including the ID."""
    try:
        token_data = decode_access_token(token)
        query = select(User).where(User.id == uuid.UUID(token_data.sub))
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return user # Pydantic will automatically convert the User model to UserResponse

    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/recover-password")
async def recover_password(request: schemas.PasswordRecoveryRequest, db: AsyncSession = Depends(get_db)):
    query = select(User).where(User.email == request.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        reset_code = str(random.randint(100000, 999999))
        await redis_client.setex(f"pwd_reset_{user.email}", 900, reset_code)
        
        # In production, integrate an email service like SendGrid here
        print(f"\n[EMAIL] TO: {user.email} | CODE: {reset_code}")

    return {"status": "Recovery email dispatched if account exists."}

@router.post("/reset-password")
async def reset_password(request: schemas.PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    stored_code = await redis_client.get(f"pwd_reset_{request.email}")
    
    if not stored_code or stored_code.decode("utf-8") != request.code:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
        
    query = select(User).where(User.email == request.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    user.hashed_password = get_password_hash(request.new_password)
    await db.commit()
    await redis_client.delete(f"pwd_reset_{request.email}")
    
    return {"status": "Password successfully reset."}