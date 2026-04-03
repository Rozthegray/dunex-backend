"""
Dunex Markets — Admin Router
Full platform control: site settings, user management, KYC review, balances, and order processing.
All endpoints require role == 'admin' or 'superadmin'.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.session import get_db
from app.core.security import get_current_user
from app.domains.users.models import User, SiteSettings
from app.domains.wallet.models import Wallet, LedgerTransaction, PaymentMethod

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Admin Guard
# ---------------------------------------------------------------------------

async def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


# ---------------------------------------------------------------------------
# Platform (Site) Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_site_settings(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SiteSettings))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = SiteSettings()
        db.add(settings)
        await db.commit()
    return {
        "trading_enabled": settings.trading_enabled,
        "withdrawals_enabled": settings.withdrawals_enabled,
        "deposits_enabled": settings.deposits_enabled,
        "maintenance_mode": settings.maintenance_mode,
        "maintenance_message": settings.maintenance_message,
        "supported_currencies": settings.supported_currencies,
        "kyc_required_for_withdrawal": settings.kyc_required_for_withdrawal,
        "min_withdrawal_usd": settings.min_withdrawal_usd,
        "max_withdrawal_usd": settings.max_withdrawal_usd,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


class SiteSettingsUpdate(BaseModel):
    trading_enabled: Optional[bool] = None
    withdrawals_enabled: Optional[bool] = None
    deposits_enabled: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    maintenance_message: Optional[str] = None
    supported_currencies: Optional[list] = None
    kyc_required_for_withdrawal: Optional[bool] = None
    min_withdrawal_usd: Optional[str] = None
    max_withdrawal_usd: Optional[str] = None

@router.patch("/settings")
async def update_site_settings(
    payload: SiteSettingsUpdate,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SiteSettings))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = SiteSettings()
        db.add(settings)

    updates = payload.dict(exclude_none=True)
    for key, value in updates.items():
        setattr(settings, key, value)

    await db.commit()
    return {"status": "ok", "updated": list(updates.keys())}


@router.get("/settings/public")
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SiteSettings))
    settings = result.scalar_one_or_none()
    if not settings:
        return {"maintenance_mode": False, "trading_enabled": True, "supported_currencies": ["USD", "NGN", "BTC", "USDT"]}
    return {
        "maintenance_mode": settings.maintenance_mode,
        "maintenance_message": settings.maintenance_message,
        "trading_enabled": settings.trading_enabled,
        "withdrawals_enabled": settings.withdrawals_enabled,
        "deposits_enabled": settings.deposits_enabled,
        "supported_currencies": settings.supported_currencies,
        "kyc_required_for_withdrawal": settings.kyc_required_for_withdrawal,
    }


# ---------------------------------------------------------------------------
# User Management & Identity Matrix
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    page: int = 1,
    limit: int = 50,
    kyc_status: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(User)
    
    if kyc_status:
        q = q.where(User.kyc_status == kyc_status)
    if role:
        q = q.where(User.role == role)
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    if search:
        q = q.where(User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%"))
        
    count_query = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    q = q.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    users = (await db.execute(q)).scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "kyc_status": u.kyc_status,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        valid_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")
        
    # Join the referrer to display in the Identity Matrix
    query = select(User).where(User.id == valid_uuid).options(joinedload(User.referred_by))
    user = (await db.execute(query)).scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    wallet_query = select(Wallet).where(Wallet.user_id == valid_uuid).limit(1)
    wallet = (await db.execute(wallet_query)).scalar_one_or_none()

    balances = {
        "main": wallet.main_balance if wallet else 0.0,
        "profit": wallet.profit_balance if wallet else 0.0,
        "bonus": wallet.bonus_balance if wallet else 0.0,
        "referral": wallet.referral_balance if wallet else 0.0,
    }
    total_equity = sum(balances.values())

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "kyc_status": user.kyc_status,
        "is_active": user.is_active,
        "dob": getattr(user, 'dob', ''),
        "gender": getattr(user, 'gender', ''),
        "phone": getattr(user, 'phone', ''),
        "address": getattr(user, 'address', ''),
        "country": getattr(user, 'country', ''),
        "id_number": getattr(user, 'id_number', getattr(user, 'ssn', '')),
        "id_card_url": user.id_card_url,
        "govt_id_url": user.govt_id_url,
        "referral_code": getattr(user, 'referral_code', 'N/A'),
        "referred_by_email": user.referred_by.email if user.referred_by else None,
        "referred_by_code": user.referred_by.referral_code if user.referred_by else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "balances": balances,
        "total_equity": total_equity
    }


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    idNumber: Optional[str] = None
    referred_by_code: Optional[str] = None

@router.patch("/users/{user_id}")
async def update_user_profile(
    user_id: str, 
    payload: AdminUserUpdate, 
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    try:
        valid_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    user = (await db.execute(select(User).where(User.id == valid_uuid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.full_name is not None: user.full_name = payload.full_name
    if payload.email is not None: user.email = payload.email
    if payload.dob is not None: user.dob = payload.dob
    if payload.gender is not None: user.gender = payload.gender
    if payload.phone is not None: user.phone = payload.phone
    if payload.address is not None: user.address = payload.address
    if payload.country is not None: user.country = payload.country
    if payload.idNumber is not None: 
        user.id_number = payload.idNumber
        user.ssn = payload.idNumber # Keep legacy sync

    # Admin Manual Referral Override
    if payload.referred_by_code:
        code = payload.referred_by_code.strip().upper()
        if code == getattr(user, 'referral_code', ''):
            raise HTTPException(status_code=400, detail="User cannot refer themselves.")
        referrer = (await db.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
        if referrer:
            user.referred_by_id = referrer.id
        else:
            raise HTTPException(status_code=404, detail="Referrer code not found.")
    elif payload.referred_by_code == "":
        user.referred_by_id = None

    await db.commit()
    return {"status": "success", "message": "Identity Matrix Updated"}


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = False
    await db.commit()
    return {"status": "suspended"}

@router.post("/users/{user_id}/reactivate")
async def reactivate_user(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = True
    await db.commit()
    return {"status": "reactivated"}

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found.")
    await db.delete(user)
    await db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Balance Adjustments (4-Balance Ledger)
# ---------------------------------------------------------------------------

class BalanceAdjustRequest(BaseModel):
    amount: float
    action: str  # 'add' or 'subtract'
    wallet_type: str = "main"

@router.post("/users/{user_id}/balance")
async def adjust_user_balance(
    user_id: str,
    payload: BalanceAdjustRequest,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.amount <= 0: raise HTTPException(status_code=400, detail="Amount must be > 0.")
    if payload.action not in ("add", "subtract"): raise HTTPException(status_code=400, detail="Invalid action.")
    if payload.wallet_type not in ("main", "profit", "bonus", "referral"): raise HTTPException(status_code=400, detail="Invalid wallet.")

    user_uuid = uuid.UUID(user_id)
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user_uuid).limit(1))).scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=user_uuid, currency="USD")
        db.add(wallet)
        await db.flush()

    column_name = f"{payload.wallet_type}_balance"
    current_balance = getattr(wallet, column_name)

    if payload.action == "add":
        new_balance = current_balance + payload.amount
        tx_type = "deposit"
    elif payload.action == "subtract":
        if current_balance < payload.amount:
            raise HTTPException(status_code=400, detail=f"Insufficient funds in {payload.wallet_type}.")
        new_balance = current_balance - payload.amount
        tx_type = "withdrawal"

    setattr(wallet, column_name, new_balance)

    tx = LedgerTransaction(
        wallet_id=wallet.id,
        amount=payload.amount,
        transaction_type=tx_type,
        wallet_type=payload.wallet_type,
        status="completed", 
        reference=f"ADM-{uuid.uuid4().hex[:8].upper()}"
    )
    db.add(tx)
    await db.commit()

    return {"status": "success", "new_balance": new_balance}

@router.get("/users/{user_id}/transactions")
async def get_user_transactions(user_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == uuid.UUID(user_id)).limit(1))).scalar_one_or_none()
    if not wallet: return []

    txs = (await db.execute(
        select(LedgerTransaction).where(LedgerTransaction.wallet_id == wallet.id).order_by(LedgerTransaction.created_at.desc())
    )).scalars().all()

    return [
        {
            "id": str(t.id),
            "transaction_type": t.transaction_type,
            "reference": t.reference,
            "amount": float(t.amount),
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None
        } for t in txs
    ]


# ---------------------------------------------------------------------------
# Order & Affiliate Clearinghouse
# ---------------------------------------------------------------------------

@router.get("/orders")
async def get_orders(status: Optional[str] = "pending", _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    q = select(LedgerTransaction).options(joinedload(LedgerTransaction.wallet).joinedload(Wallet.owner))
    if status and status != "all": q = q.where(LedgerTransaction.status == status)
    q = q.order_by(LedgerTransaction.created_at.desc())
    
    orders = (await db.execute(q)).scalars().all()

    return [
        {
            "id": str(o.id),
            "wallet_id": str(o.wallet_id),
            "amount": float(o.amount),
            "transaction_type": o.transaction_type,
            "status": o.status,
            "reference": o.reference,
            "proof_url": o.proof_url,
            "destination_details": o.destination_details,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "user": {
                "full_name": o.wallet.owner.full_name if o.wallet.owner.full_name else "Unknown",
                "email": o.wallet.owner.email,
                "kyc_status": o.wallet.owner.kyc_status
            } if o.wallet and o.wallet.owner else None
        } for o in orders
    ]


@router.post("/orders/{order_id}/{action}")
async def process_order(order_id: str, action: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Approves/rejects orders AND powers the Affiliate Referral Engine."""
    if action not in ["approve", "reject"]: raise HTTPException(status_code=400, detail="Invalid action.")

    tx = (await db.execute(select(LedgerTransaction).where(LedgerTransaction.id == uuid.UUID(order_id)))).scalar_one_or_none()
    if not tx: raise HTTPException(status_code=404, detail="Order not found.")
    if tx.status != "pending": raise HTTPException(status_code=400, detail=f"Order is already {tx.status}.")

    wallet = (await db.execute(select(Wallet).where(Wallet.id == tx.wallet_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == wallet.user_id))).scalar_one_or_none()

    if action == "approve":
        tx.status = "completed"
        if tx.transaction_type == "deposit":
            wallet.main_balance += tx.amount
            
            # 🚨 AUTOMATED AFFILIATE COMMISSION ENGINE 🚨
            if user and user.referred_by_id:
                commission_amount = tx.amount * 0.10 # 10% Cut
                
                referrer_wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.referred_by_id).limit(1))).scalar_one_or_none()
                if referrer_wallet:
                    referrer_wallet.referral_balance += commission_amount
                    
                    comm_tx = LedgerTransaction(
                        wallet_id=referrer_wallet.id,
                        amount=commission_amount,
                        transaction_type="deposit",
                        wallet_type="referral",
                        status="completed",
                        reference=f"COMM-{uuid.uuid4().hex[:8].upper()}",
                        destination_details=f"10% Affiliate Commission from deposit by {user.email}"
                    )
                    db.add(comm_tx)
            
    elif action == "reject":
        tx.status = "rejected"
        if tx.transaction_type == "withdrawal":
            wallet.main_balance += tx.amount # Refund the requested withdrawal

    await db.commit()
    return {"status": "success", "message": f"Order {action.upper()}D successfully."}


# ---------------------------------------------------------------------------
# Payment Gateways Management
# ---------------------------------------------------------------------------

class PaymentMethodCreateUpdate(BaseModel):
    name: str
    method_type: str
    account_details: str
    instructions: Optional[str] = None

@router.get("/payment-methods")
async def get_admin_payment_methods(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(PaymentMethod).order_by(PaymentMethod.name))).scalars().all()

@router.post("/payment-methods")
async def create_payment_method(payload: PaymentMethodCreateUpdate, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    new_method = PaymentMethod(**payload.dict())
    db.add(new_method)
    await db.commit()
    return {"status": "success", "id": str(new_method.id)}

@router.put("/payment-methods/{method_id}")
async def update_payment_method(method_id: str, payload: PaymentMethodCreateUpdate, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method: raise HTTPException(status_code=404, detail="Not found.")
    
    method.name = payload.name
    method.method_type = payload.method_type
    method.account_details = payload.account_details
    method.instructions = payload.instructions
    await db.commit()
    return {"status": "success"}

@router.patch("/payment-methods/{method_id}")
async def toggle_payment_method(method_id: str, is_active: bool, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method: raise HTTPException(status_code=404, detail="Not found.")
    method.is_active = is_active
    await db.commit()
    return {"status": "success"}

@router.delete("/payment-methods/{method_id}")
async def delete_payment_method(method_id: str, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method: raise HTTPException(status_code=404, detail="Not found.")
    await db.delete(method)
    await db.commit()
    return {"status": "success"}

# ---------------------------------------------------------------------------
# KYC Review & Stats
# ---------------------------------------------------------------------------

class KYCDecision(BaseModel):
    status: str
    reason: Optional[str] = None

@router.post("/users/{user_id}/kyc-review")
async def review_kyc(user_id: str, payload: KYCDecision, _admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if payload.status not in ("verified", "rejected"): raise HTTPException(status_code=400, detail="Invalid status.")
    
    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found.")
    
    user.kyc_status = payload.status
    await db.commit()
    return {"status": "ok"}

@router.get("/stats")
async def get_dashboard_stats(_admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    pending_kyc = (await db.execute(select(func.count(User.id)).where(User.kyc_status == "pending"))).scalar()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "pending_kyc": pending_kyc,
        "open_tickets": 0,
        "unread_chats": 0,
    }
