import uuid
import os
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.core.security import get_current_user
from app.core.idempotency import IdempotentRoute
from app.domains.users.models import User
from app.domains.wallet.models import Wallet, PaymentMethod, LedgerTransaction
from app.domains.wallet import schemas, services

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

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

    # 🚨 FIXED: Now uses main_balance
    return {"cached_balance": wallet.main_balance, "currency": wallet.currency, "wallet_id": str(wallet.id)}

@router.post("/deposit")
async def request_deposit(
    amount: float = Form(...),
    payment_method_id: str = Form(...),
    proof_image: UploadFile = File(...), # 🚨 Frontend must use 'proof_image'
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(None, alias="Idempotency-Key") # 🚨 Made optional so it doesn't break
):
    try:
        query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
        wallet = (await db.execute(query)).scalar_one_or_none()
        
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found.")

        # 🚨 Safety Net: Create folder if it doesn't exist
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        file_ext = proof_image.filename.split(".")[-1] if proof_image.filename else "jpg"
        file_name = f"{uuid.uuid4().hex}.{file_ext}"
        file_path = f"{UPLOAD_DIR}/{file_name}"
        
        image_data = await proof_image.read()
        with open(file_path, "wb") as f:
            f.write(image_data)
            
        proof_url = f"/{UPLOAD_DIR}/{file_name}"
        reference = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        
        await services.execute_deposit(db, wallet.id, amount, reference, uuid.UUID(payment_method_id), proof_url)
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
    # 🚨 STRICT KYC GUARD: Server will reject if not verified
    if current_user.kyc_status != "verified":
        raise HTTPException(
            status_code=403, 
            detail="KYC Verification Required. You must complete identity verification before withdrawing funds."
        )

    query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
    wallet = (await db.execute(query)).scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    reference = f"WDW-{uuid.uuid4().hex[:12].upper()}"

    await services.execute_withdrawal(
        db=db, 
        wallet_id=wallet.id, 
        amount=payload.amount, 
        reference=reference,
        destination_details=payload.destination_details 
    )
    
    await db.refresh(wallet)

    return schemas.TransactionResponse(
        status="pending", 
        reference=reference,
        amount=payload.amount,
        new_balance=wallet.main_balance, # 🚨 FIXED
        message="Withdrawal request submitted and is pending review."
    )

@router.get("/summary")
async def get_wallet_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Provides the 4-balance breakdown for the mobile app dashboard."""
    query = select(Wallet).where(Wallet.user_id == current_user.id).limit(1)
    wallet = (await db.execute(query)).scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=current_user.id, currency="USD")
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    total_equity = wallet.main_balance + wallet.profit_balance + wallet.bonus_balance + wallet.referral_balance

    return {
        "total_equity": total_equity,
        "balances": {
            "main": wallet.main_balance,
            "profit": wallet.profit_balance,
            "bonus": wallet.bonus_balance,
            "referral": wallet.referral_balance
        }
    }
