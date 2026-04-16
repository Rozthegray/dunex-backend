import random
import string
import uuid
from datetime import timedelta
from typing import Optional

# 🚨 Consolidated FastAPI Imports
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.core.security import verify_password, create_access_token, get_password_hash, decode_access_token
from app.core.redis import redis_client

# 🚨 Import BOTH email functions
from app.core.email import send_onboarding_email, send_password_reset_email

# Import models and new schemas
from app.domains.users.models import User
from app.domains.wallet.models import Wallet
from app.domains.users import schemas

router = APIRouter(tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def generate_referral_code():
    """Generates a secure 8-character alphanumeric referral code."""
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"DNX-{chars}"

class ExtendedRegisterRequest(schemas.RegisterRequest):
    referral_code: Optional[str] = None

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
            detail="Incorrect email or passphrase.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account suspended. Contact support.")

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
async def register_user(
    request: ExtendedRegisterRequest, 
    background_tasks: BackgroundTasks, # 🚨 Injected BackgroundTasks
    db: AsyncSession = Depends(get_db)
):
    """Creates a new user, links referrals, provisions a wallet, and sends email."""
    
    # 🚨 BACKEND VALIDATION (Feeds the frontend warning popups)
    if not request.full_name or not request.password or not request.email:
        raise HTTPException(status_code=400, detail="All identity fields must be populated.")
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Passphrase must be at least 8 characters.")

    safe_email = request.email.lower().strip()
    
    query = select(User).where(User.email == safe_email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered.")

    # 🚨 REFERRAL SYSTEM
    referrer_id = None
    if request.referral_code:
        clean_code = request.referral_code.strip().upper()
        ref_query = select(User).where(User.referral_code == clean_code)
        referrer = (await db.execute(ref_query)).scalar_one_or_none()
        if referrer:
            referrer_id = referrer.id

    new_user = User(
        email=safe_email,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role="user",
        referral_code=generate_referral_code(),
        referred_by_id=referrer_id              
    )
    db.add(new_user)
    await db.flush() 
    
    # 🚨 4-BALANCE WALLET SETUP
    new_wallet = Wallet(
        user_id=new_user.id, 
        currency="USD", 
        main_balance=0.0,
        profit_balance=0.0,
        bonus_balance=0.0,
        referral_balance=0.0
    )
    db.add(new_wallet)
    await db.commit()

    # 🚨 DISPATCH ONBOARDING EMAIL VIA MAILTRAP
    background_tasks.add_task(send_onboarding_email, safe_email, request.full_name)

    return {"status": "success", "message": "User registered successfully"}

@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_profile(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
):
    """Returns the profile of the currently logged-in user."""
    try:
        token_data = decode_access_token(token)
        query = select(User).where(User.id == uuid.UUID(token_data.sub))
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return user 

    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/recover-password")
async def recover_password(
    request: schemas.PasswordRecoveryRequest, 
    background_tasks: BackgroundTasks, # 🚨 Injected BackgroundTasks
    db: AsyncSession = Depends(get_db)
):
    """Generates a 6-digit code and fires it via Mailtrap."""
    query = select(User).where(User.email == request.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        reset_code = str(random.randint(100000, 999999))
        await redis_client.setex(f"pwd_reset_{user.email}", 900, reset_code)
        
        # 🚨 DISPATCH RECOVERY EMAIL VIA MAILTRAP
        background_tasks.add_task(send_password_reset_email, user.email, reset_code)

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
        
    # 🚨 Swapped back to request.new_password
    user.hashed_password = get_password_hash(request.new_password)
    
    await db.commit()
    await redis_client.delete(f"pwd_reset_{request.email}")
    
    return {"status": "Password successfully reset."}
@router.post("/secret-seed-superadmin", include_in_schema=False)
async def trigger_admin_seed(
    secret_key: str = Header(None), 
    db: AsyncSession = Depends(get_db)
):
    if secret_key != "MySuperSecretDeploymentKey999!":
        raise HTTPException(status_code=403, detail="Forbidden")

    admin_email = "adminmaster@dunexmarkets.com"
    
    query = select(User).where(User.email == admin_email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        return {"status": "Already seeded"}

    superadmin = User(
        email=admin_email,
        hashed_password=get_password_hash("DunexMasterBABA2020SIX!"),
        full_name="Chief Administrator",
        role="superadmin",
        is_active=True,
        kyc_status="verified"
    )
    db.add(superadmin)
    await db.flush()

    admin_wallet = Wallet(
        user_id=superadmin.id,
        currency="USD",
        main_balance=0.0,
        profit_balance=0.0,
        bonus_balance=0.0,
        referral_balance=0.0
    )
    db.add(admin_wallet)
    
    await db.commit()
    return {"status": "Superadmin successfully
