"""
Dunex Markets — User Settings Router
Covers: profile update, password change, avatar, 2FA, push token, KYC,
        payment methods (card/bank/crypto), wallet management.
"""
import uuid
import random
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.core.security import get_current_user, verify_password, get_password_hash
from app.core.redis import redis_client
from app.domains.users.models import User
from app.domains.wallet.models import Wallet, PaymentMethod

router = APIRouter(prefix="/users", tags=["User Settings"])


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    base_currency: Optional[str] = None


@router.patch("/me")
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip()
    if payload.base_currency is not None:
        current_user.base_currency = payload.base_currency
    await db.commit()
    return {"status": "ok", "full_name": current_user.full_name, "base_currency": current_user.base_currency}


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload profile avatar. In production: stream to S3 and save URL."""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG/WebP images are accepted.")

    # Production: upload to S3
    # import boto3
    # s3 = boto3.client("s3")
    # key = f"avatars/{current_user.id}.jpg"
    # s3.upload_fileobj(file.file, "dunex-media", key)
    # url = f"https://dunex-media.s3.amazonaws.com/{key}"

    # Stub for now
    url = f"https://api.dunexmarkets.com/media/avatars/{current_user.id}.jpg"
    current_user.avatar_url = url
    await db.commit()
    return {"status": "ok", "avatar_url": url}


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return {"status": "ok", "message": "Password updated successfully."}


# ---------------------------------------------------------------------------
# 2FA (email OTP)
# ---------------------------------------------------------------------------

@router.post("/enable-2fa")
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sends OTP to email, user must confirm via /verify-2fa."""
    otp = str(random.randint(100000, 999999))
    await redis_client.setex(f"2fa_setup_{current_user.id}", 600, otp)

    # In production: send via SendGrid
    print(f"\n[2FA OTP] TO: {current_user.email} | CODE: {otp} (expires 10 min)\n")
    return {"status": "otp_sent", "message": "Check your email for the verification code."}


class OTPVerify(BaseModel):
    code: str


@router.post("/verify-2fa")
async def verify_2fa(
    payload: OTPVerify,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stored = await redis_client.get(f"2fa_setup_{current_user.id}")
    if not stored or stored.decode() != payload.code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    current_user.two_fa_enabled = True
    await db.commit()
    await redis_client.delete(f"2fa_setup_{current_user.id}")
    return {"status": "ok", "message": "2FA enabled successfully."}


@router.post("/disable-2fa")
async def disable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.two_fa_enabled = False
    await db.commit()
    return {"status": "ok", "message": "2FA disabled."}


# ---------------------------------------------------------------------------
# Expo push token
# ---------------------------------------------------------------------------

class PushTokenUpdate(BaseModel):
    token: str


@router.post("/push-token")
async def save_push_token(
    payload: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.expo_push_token = payload.token
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# KYC
# ---------------------------------------------------------------------------

@router.post("/kyc")
async def submit_kyc(
    id_front: UploadFile = File(...),
    id_back: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept KYC documents and queue for admin review."""
    # Production: upload to S3, store URLs, trigger admin notification
    current_user.kyc_status = "pending"
    await db.commit()
    return {"status": "ok", "kyc_status": "pending", "message": "Documents submitted. Review takes 1-2 business days."}


@router.get("/kyc/status")
async def get_kyc_status(current_user: User = Depends(get_current_user)):
    return {"kyc_status": current_user.kyc_status}


# ---------------------------------------------------------------------------
# Payment methods
# ---------------------------------------------------------------------------

class PaymentMethodCreate(BaseModel):
    type: str     # 'card' | 'bank' | 'crypto'
    label: str
    details: dict
    is_primary: bool = False


@router.get("/payment-methods")
async def list_payment_methods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentMethod).where(PaymentMethod.user_id == current_user.id)
    )
    methods = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "type": m.type,
            "label": m.label,
            "is_primary": m.is_primary,
            "created_at": m.created_at.isoformat(),
        }
        for m in methods
    ]


@router.post("/payment-methods")
async def add_payment_method(
    payload: PaymentMethodCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.is_primary:
        # Unset existing primary
        from sqlalchemy import update
        await db.execute(
            update(PaymentMethod)
            .where(PaymentMethod.user_id == current_user.id, PaymentMethod.type == payload.type)
            .values(is_primary=False)
        )

    method = PaymentMethod(
        user_id=current_user.id,
        type=payload.type,
        label=payload.label,
        details=payload.details,
        is_primary=payload.is_primary,
    )
    db.add(method)
    await db.commit()
    return {"status": "ok", "id": str(method.id)}


@router.delete("/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentMethod).where(
            PaymentMethod.id == uuid.UUID(method_id),
            PaymentMethod.user_id == current_user.id,
        )
    )
    method = result.scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found.")
    await db.delete(method)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Wallets
# ---------------------------------------------------------------------------

@router.get("/wallets")
async def get_wallets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallets = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "currency": w.currency,
            "balance": float(w.cached_balance),
            "wallet_address": w.wallet_address,
            "is_primary": w.is_primary,
        }
        for w in wallets
    ]

from fastapi import Form

# ---------------------------------------------------------------------------
# KYC
# ---------------------------------------------------------------------------

@router.post("/kyc")
async def submit_kyc(
    dob: str = Form(...),
    ssn: str = Form(...),
    id_card: UploadFile = File(...),
    govt_id: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept full KYC details and documents."""
    
    # In production, you would upload these files to AWS S3 or Cloudinary here
    # and save the returned URLs to the database. For now, we simulate the URLs.
    simulated_id_url = f"https://dunex.com/secure/id_{current_user.id}.jpg"
    simulated_govt_url = f"https://dunex.com/secure/govt_{current_user.id}.jpg"

    current_user.dob = dob
    current_user.ssn = ssn
    current_user.id_card_url = simulated_id_url
    current_user.govt_id_url = simulated_govt_url
    current_user.kyc_status = "pending"
    
    await db.commit()
    return {"status": "ok", "kyc_status": "pending", "message": "KYC submitted. Review takes 1-2 business days."}

@router.get("/kyc/status")
async def get_kyc_status(current_user: User = Depends(get_current_user)):
    return {"kyc_status": current_user.kyc_status}