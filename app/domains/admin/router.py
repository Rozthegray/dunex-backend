"""
Dunex Markets — Admin Router
Full platform control: site settings, user management, KYC review, suspend/reactivate.
All endpoints require role == 'admin' or 'superadmin'.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.domains.chat.models import ChatMessage, SupportTicket
from app.db.session import get_db
from app.core.security import get_current_user
from app.domains.users.models import User, SiteSettings
from app.domains.wallet.models import Wallet, LedgerTransaction, PaymentMethod
router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Admin guard
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
        # Auto-create default row
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


# Public endpoint — mobile app reads this to know feature flags
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
# User management
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    page: int = 1,
    limit: int = 50,
    kyc_status: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None, # Added to support the sidebar links!
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 1. Build the base query
    q = select(User)
    
    # 2. Apply all filters
    if kyc_status:
        q = q.where(User.kyc_status == kyc_status)
    if role:
        q = q.where(User.role == role)
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    if search:
        q = q.where(User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%"))
        
    # 3. Count the total records matching these specific filters
    count_query = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 4. Apply Ordering FIRST, then Offset/Limit (CRITICAL SQL FIX)
    q = q.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(q)
    users = result.scalars().all()

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
                "created_at": u.created_at.isoformat(),
                # Removed last_login_at to prevent server crashes
            }
            for u in users
        ],
    }


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, db: AsyncSession = Depends(get_db)):
    # 🛑 THE FIX: Safely check if the ID is a valid UUID first!
    try:
        valid_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format. Must be a valid UUID.")
        
    result = await db.execute(select(User).where(User.id == valid_uuid))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user



@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = False
    await db.commit()
    return {"status": "suspended", "email": user.email}


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = True
    await db.commit()
    return {"status": "reactivated", "email": user.email}


class RoleUpdate(BaseModel):
    role: str  # 'user' | 'admin'


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: RoleUpdate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can change roles.")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.role = payload.role
    await db.commit()
    return {"status": "ok", "role": user.role}


# ---------------------------------------------------------------------------
# KYC Review
# ---------------------------------------------------------------------------

class KYCDecision(BaseModel):
    status: str   # 'verified' | 'rejected'
    reason: Optional[str] = None


@router.post("/users/{user_id}/kyc-review")
async def review_kyc(
    user_id: str,
    payload: KYCDecision,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.status not in ("verified", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'verified' or 'rejected'.")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.kyc_status = payload.status
    await db.commit()

    # Send push notification to user
    if user.expo_push_token:
        from app.core.notifications import send_push_to_user
        msg = "Your KYC has been verified! You can now withdraw." if payload.status == "verified" else f"KYC rejected: {payload.reason or 'Please resubmit.'}"
        await send_push_to_user(user.expo_push_token, "KYC Update", msg, db, user_id=user.id)

    return {"status": "ok", "kyc_status": payload.status}


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_dashboard_stats(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    pending_kyc = (await db.execute(select(func.count(User.id)).where(User.kyc_status == "pending"))).scalar()
    
    # 🚨 Temporarily hardcode these to 0 until we build the Support system!
    open_tickets = 0
    unread_chats = 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "pending_kyc": pending_kyc,
        "open_tickets": open_tickets,
        "unread_chats": unread_chats,
    }
# ---------------------------------------------------------------------------
# Balance & Liquidity Adjustments
# ---------------------------------------------------------------------------

class BalanceAdjustRequest(BaseModel):
    amount: float
    action: str  # 'add' or 'subtract'

@router.post("/users/{user_id}/balance")
async def adjust_user_balance(
    user_id: str,
    payload: BalanceAdjustRequest,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    if payload.action not in ("add", "subtract"):
        raise HTTPException(status_code=400, detail="Action must be 'add' or 'subtract'.")

    # 1. Validate UUID
    try:
        valid_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    # 2. Get the User's Wallet
    result = await db.execute(select(Wallet).where(Wallet.user_id == valid_uuid).limit(1))
    wallet = result.scalar_one_or_none()

    # If they somehow don't have a wallet, provision one instantly
    if not wallet:
        wallet = Wallet(user_id=valid_uuid, currency="USD", cached_balance=0.0)
        db.add(wallet)
        await db.flush()

    # 3. Adjust the Balance
    if payload.action == "add":
        wallet.cached_balance += payload.amount
    elif payload.action == "subtract":
        if wallet.cached_balance < payload.amount:
            raise HTTPException(status_code=400, detail="Insufficient funds. Cannot subtract more than the current balance.")
        wallet.cached_balance -= payload.amount

    # 4. Create a Ledger Transaction for History
    tx = LedgerTransaction(
        wallet_id=wallet.id,
        amount=payload.amount,
        transaction_type="deposit" if payload.action == "add" else "withdrawal",
        status="completed", # Admin overrides are instantly marked as completed
        reference=f"ADM-{uuid.uuid4().hex[:8].upper()}"
    )
    db.add(tx)

    await db.commit()

    return {
        "status": "success",
        "message": f"Successfully {'added' if payload.action == 'add' else 'subtracted'} ${payload.amount:,.2f}.",
        "new_balance": wallet.cached_balance
    }

@router.get("/users/{user_id}/transactions")
async def get_user_transactions(
    user_id: str,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetches all ledger history for a specific user to display in the Admin Dashboard."""
    try:
        valid_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    # Find the wallet first
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == valid_uuid).limit(1))).scalar_one_or_none()
    
    if not wallet:
        return [] # No wallet = no transactions

    # Fetch transactions linked to that wallet
    txs = (await db.execute(
        select(LedgerTransaction)
        .where(LedgerTransaction.wallet_id == wallet.id)
        .order_by(LedgerTransaction.created_at.desc())
    )).scalars().all()

    return [
        {
            "id": str(t.id),
            "transaction_type": t.transaction_type,
            "reference": t.reference,
            "amount": float(t.amount),
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in txs
    ]

# ---------------------------------------------------------------------------
# Order & Liquidity Clearinghouse
# ---------------------------------------------------------------------------

from sqlalchemy.orm import joinedload # 🚨 Make sure to import this at the top

@router.get("/orders")
async def get_orders(
    status: Optional[str] = "pending",
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetches Ledger Transactions and joins the User data for the Admin Dashboard."""
    
    # 🚨 CRITICAL FIX: joinedload tells the DB to fetch the Wallet AND the User (owner) attached to the transaction!
    q = (
        select(LedgerTransaction)
        .options(joinedload(LedgerTransaction.wallet).joinedload(Wallet.owner))
    )
    
    if status and status != "all":
        q = q.where(LedgerTransaction.status == status)
        
    q = q.order_by(LedgerTransaction.created_at.desc())
    
    result = await db.execute(q)
    orders = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "wallet_id": str(o.wallet_id),
            "amount": float(o.amount),
            "transaction_type": o.transaction_type,
            "status": o.status,
            "reference": o.reference,
            "proof_url": o.proof_url,
            "destination_details": o.destination_details, # 🚨 Now this will show up on the frontend!
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "user": {
                "full_name": o.wallet.owner.full_name if o.wallet.owner.full_name else "System Auto-Generated",
                "email": o.wallet.owner.email,
                "kyc_status": o.wallet.owner.kyc_status
            } if o.wallet and o.wallet.owner else None
        }
        for o in orders
    ]
@router.post("/orders/{order_id}/{action}")
async def process_order(
    order_id: str,
    action: str, 
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Safely approves or rejects a user deposit/withdrawal and balances the ledger."""
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'.")

    try:
        valid_uuid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order ID.")

    # 1. Fetch the transaction
    tx = (await db.execute(select(LedgerTransaction).where(LedgerTransaction.id == valid_uuid))).scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Order not found.")

    if tx.status != "pending":
        raise HTTPException(status_code=400, detail=f"Order has already been processed as {tx.status.upper()}.")

    # 2. Fetch the target Wallet
    wallet = (await db.execute(select(Wallet).where(Wallet.id == tx.wallet_id))).scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Associated wallet not found.")

    # 3. Execute Secure Ledger Math
    if action == "approve":
        tx.status = "completed"
        # Only ADD funds if it is a deposit. (Withdrawals are already deducted when requested).
        if tx.transaction_type == "deposit":
            wallet.cached_balance += tx.amount
            
    elif action == "reject":
        tx.status = "rejected"
        # If we reject a withdrawal, we must REFUND the money back to the user's wallet.
        if tx.transaction_type == "withdrawal":
            wallet.cached_balance += tx.amount

    await db.commit()
    
    return {"status": "success", "message": f"Order {action.upper()}D successfully."}
# ---------------------------------------------------------------------------
# Payment Gateways Management (CRUD)
# ---------------------------------------------------------------------------

class PaymentMethodCreateUpdate(BaseModel):
    name: str
    method_type: str
    account_details: str
    instructions: Optional[str] = None

@router.get("/payment-methods")
async def get_admin_payment_methods(
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    """Fetches all payment methods, including inactive ones, for admin management."""
    # 🚨 CHANGED: Ordering by 'name' instead of 'created_at' to prevent the crash!
    result = await db.execute(select(PaymentMethod).order_by(PaymentMethod.name))
    return result.scalars().all()

@router.post("/payment-methods")
async def create_payment_method(
    payload: PaymentMethodCreateUpdate, 
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    """Creates a new payment gateway."""
    new_method = PaymentMethod(**payload.dict())
    db.add(new_method)
    await db.commit()
    return {"status": "success", "id": str(new_method.id)}

@router.put("/payment-methods/{method_id}")
async def update_payment_method(
    method_id: str, 
    payload: PaymentMethodCreateUpdate, 
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    """Updates an existing payment gateway's details."""
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found.")
    
    method.name = payload.name
    method.method_type = payload.method_type
    method.account_details = payload.account_details
    method.instructions = payload.instructions
    
    await db.commit()
    return {"status": "success"}

@router.patch("/payment-methods/{method_id}")
async def toggle_payment_method(
    method_id: str, 
    is_active: bool, 
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    """Activates or Deactivates a payment gateway instantly."""
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found.")
    
    method.is_active = is_active
    await db.commit()
    return {"status": "success", "is_active": is_active}

@router.delete("/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: str, 
    _admin=Depends(require_admin), 
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes a payment gateway."""
    method = await db.get(PaymentMethod, uuid.UUID(method_id))
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found.")
    
    await db.delete(method)
    await db.commit()
    return {"status": "success"}