import uuid
import os
import httpx
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.core.security import get_current_user
from app.core.idempotency import IdempotentRoute
from app.domains.users.models import User
from app.core.email import send_lockdown_warning_email, send_lockdown_execution_email
from app.domains.wallet.models import Wallet, PaymentMethod, LedgerTransaction
from app.domains.wallet import schemas, services

# ─────────────────────────────────────────────────────────────────────────────
# Cloudinary Configuration
# ─────────────────────────────────────────────────────────────────────────────
CLOUDINARY_CLOUD_NAME = "dkpicfvgv"
CLOUDINARY_UPLOAD_PRESET = "vidstream"

async def upload_to_cloudinary(file_bytes: bytes, filename: str) -> str:
    """Streams a file directly to Cloudinary and returns the permanent secure URL."""
    url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
    
    data = {"upload_preset": CLOUDINARY_UPLOAD_PRESET}
    files = {"file": (filename, file_bytes, "image/jpeg")}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data, files=files)
        if response.status_code == 200:
            return response.json()["secure_url"]
        else:
            print(f"Cloudinary Error: {response.text}")
            raise HTTPException(status_code=500, detail="Image storage service failed.")

# ─────────────────────────────────────────────────────────────────────────────
# Router Setup
# ─────────────────────────────────────────────────────────────────────────────

class AdminUserUpdate(BaseModel):
    first_name: str
    last_name: str
    email: str
    mobile: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    kyc_verified: bool
    email_verified: bool
    two_fa_enabled: bool

router = APIRouter(
    tags=["Wallet & Ledger"],
    route_class=IdempotentRoute,
    dependencies=[Depends(get_current_user)] 
)

@router.get("/payment-methods")
async def get_active_payment_methods(
    current_user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    query = select(PaymentMethod).where(PaymentMethod.is_active == True)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/history")
async def get_transaction_history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        wallet_query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
        wallet = (await db.execute(wallet_query)).scalar_one_or_none()
        
        if not wallet:
            return []

        tx_query = select(LedgerTransaction).where(LedgerTransaction.wallet_id == wallet.id).order_by(LedgerTransaction.created_at.desc())
        transactions = (await db.execute(tx_query)).scalars().all()
        
        formatted_history = []
        for tx in transactions:
            date_str = tx.created_at if isinstance(tx.created_at, str) else tx.created_at.isoformat() if tx.created_at else ""
            formatted_history.append({
                "id": str(tx.id),
                "amount": float(tx.amount) if tx.amount else 0.0, 
                "transaction_type": tx.transaction_type,
                "wallet_type": tx.wallet_type, 
                "status": tx.status,
                "reference": tx.reference,
                "created_at": date_str, 
                "proof_url": getattr(tx, "proof_url", None)
            })
            
        return formatted_history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.patch("/users/{target_user_id}")
async def update_user_profile(
    target_user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(User).where(User.id == target_user_id)
    user = (await db.execute(query)).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.full_name = f"{payload.first_name} {payload.last_name}".strip()
    user.email = payload.email
    user.kyc_status = "verified" if payload.kyc_verified else "unverified"
    user.is_active = payload.email_verified

    await db.commit()
    return {"status": "success", "message": "User profile updated successfully."}


@router.get("/my-wallet")
async def get_balance(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=current_user.id, currency="USD")
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    # 🚨 Expose lockdown state to the frontend
    return {
        "cached_balance": wallet.main_balance, 
        "currency": wallet.currency, 
        "wallet_id": str(wallet.id),
        "is_locked": getattr(wallet, "is_locked", False),
        "fine_owed": getattr(wallet, "lockdown_fine_owed", 0.0)
    }

@router.post("/deposit")
async def request_deposit(
    amount: float = Form(...),
    payment_method_id: str = Form(...),
    proof_image: UploadFile = File(...), 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(None, alias="Idempotency-Key") 
):
    try:
        query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
        wallet = (await db.execute(query)).scalar_one_or_none()
        
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found.")

        image_data = await proof_image.read()
        proof_url = await upload_to_cloudinary(image_data, proof_image.filename)
        
        reference = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        
        await services.execute_deposit(
            db=db, 
            wallet_id=wallet.id, 
            asset_symbol=wallet.currency, 
            amount=amount, 
            reference=reference, 
            payment_method_id=str(payment_method_id), 
            proof_image_url=proof_url
        )
        await db.refresh(wallet)

        return {
            "status": "pending",
            "reference": reference,
            "amount": amount,
            "new_balance": wallet.main_balance, 
            "message": "Proof uploaded! Deposit is pending review by an administrator."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/withdraw", response_model=schemas.TransactionResponse)
async def request_withdrawal(
    payload: schemas.TransactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    if current_user.kyc_status != "verified":
        raise HTTPException(
            status_code=403, 
            detail="KYC Verification Required. You must complete identity verification before withdrawing funds."
        )

    query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
    wallet = (await db.execute(query)).scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    # 🚨 SECURITY GUARD: Block withdrawal if account is locked
    if getattr(wallet, "is_locked", False):
        fine = getattr(wallet, "lockdown_fine_owed", 500.0)
        raise HTTPException(
            status_code=403, 
            detail=f"Account is locked due to inactivity. Please pay the ${fine:,.2f} fine to restore withdrawals."
        )

    reference = f"WDW-{uuid.uuid4().hex[:12].upper()}"

    await services.execute_withdrawal(
        db=db, 
        wallet_id=wallet.id, 
        asset_symbol=wallet.currency, 
        amount=payload.amount, 
        reference=reference,
        destination_details=payload.destination_details 
    )
    
    await db.refresh(wallet)

    new_total_equity = (wallet.main_balance or 0.0) + (wallet.profit_balance or 0.0) + (wallet.bonus_balance or 0.0) + (wallet.referral_balance or 0.0)

    return schemas.TransactionResponse(
        status="pending", 
        reference=reference,
        amount=payload.amount,
        new_balance=new_total_equity,
        message="Withdrawal request submitted and is pending review."
    )

@router.get("/summary")
async def get_wallet_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Provides the 4-balance breakdown and lockdown state for the mobile app dashboard."""
    query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
    wallet = (await db.execute(query)).scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=current_user.id, currency="USD")
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    total_equity = wallet.main_balance + wallet.profit_balance + wallet.bonus_balance + wallet.referral_balance

    # Calculate days inactive for frontend UI progress bar/warning
    last_deposit = getattr(wallet, "last_deposit_date", datetime.utcnow())
    if not last_deposit:
        last_deposit = datetime.utcnow()
    days_inactive = (datetime.utcnow() - last_deposit).days

    return {
        "total_equity": total_equity,
        "balances": {
            "main": wallet.main_balance,
            "profit": wallet.profit_balance,
            "bonus": wallet.bonus_balance,
            "referral": wallet.referral_balance
        },
        # 🚨 UI EXPOSURE
        "lockdown": {
            "is_locked": getattr(wallet, "is_locked", False),
            "fine_owed": getattr(wallet, "lockdown_fine_owed", 0.0),
            "days_inactive": days_inactive
        }
    }


@router.post("/admin/sweep-inactivity", tags=["Admin Cron"])
async def trigger_inactivity_sweep(db: AsyncSession = Depends(get_db)):
    """Triggered daily via external Cron to lock inactive accounts."""
    now = datetime.utcnow()
    
    # Fetch all unlocked wallets and their owners
    query = select(Wallet, User).join(User, Wallet.user_id == User.id).where(Wallet.is_locked == False)
    result = await db.execute(query)
    active_accounts = result.all()

    processed_count = 0

    for wallet, user in active_accounts:
        if not wallet.last_deposit_date:
            wallet.last_deposit_date = now
            continue

        days_inactive = (now - wallet.last_deposit_date).days

        if days_inactive == 30:
            await send_lockdown_warning_email(user.email, user.full_name or "Trader", 30)
            processed_count += 1
            
        elif days_inactive == 55:
            await send_lockdown_warning_email(user.email, user.full_name or "Trader", 5)
            processed_count += 1
            
        elif days_inactive >= 60:
            wallet.is_locked = True
            wallet.lockdown_fine_owed = 500.00
            await send_lockdown_execution_email(user.email, user.full_name or "Trader", 500.00)
            
            # Log the fine being levied on the ledger
            fine_ledger = LedgerTransaction(
                wallet_id=wallet.id,
                amount=-500.00,
                transaction_type="fee",
                wallet_type="main",
                status="pending",
                reference=f"LOCKED-{uuid.uuid4().hex[:8].upper()}",
                destination_details="Inactivity Fine Levied"
            )
            db.add(fine_ledger)
            processed_count += 1
            
    await db.commit()
    return {"status": "success", "accounts_processed": processed_count}
