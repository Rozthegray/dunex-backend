import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, desc

from app.db.session import get_db
from app.core.security import get_current_admin
from app.core.redis import redis_client
from app.domains.users.models import User, SiteSettings
from app.domains.wallet.models import LedgerTransaction, PaymentMethod, Wallet

# Initialize the router with strict RBAC
router = APIRouter(
    prefix="/admin",
    tags=["Command Center Operations"],
    dependencies=[Depends(get_current_admin)]
)

# ---------------------------------------------------------
# 1. FINANCIAL ORDERS (DEPOSITS & WITHDRAWALS)
# ---------------------------------------------------------

@router.get("/orders")
async def get_orders(
    status: Optional[str] = None, 
    transaction_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Fetches deposits and withdrawals. Can filter by status (pending/approved/rejected)."""
    query = select(LedgerTransaction).order_by(desc(LedgerTransaction.created_at))
    
    if status:
        query = query.where(LedgerTransaction.status == status)
    if transaction_type:
        query = query.where(LedgerTransaction.transaction_type == transaction_type)
        
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/orders/{order_id}/approve")
async def approve_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Approves a pending transaction. 
    If it's a withdrawal, the funds were already locked/deducted during the user's request.
    We just mark it as completed.
    """
    query = select(LedgerTransaction).where(LedgerTransaction.id == order_id)
    result = await db.execute(query)
    transaction = result.scalar_one_or_none()

    if not transaction or transaction.status != "pending":
        raise HTTPException(status_code=400, detail="Invalid or non-pending order.")

    transaction.status = "completed"
    await db.commit()
    
    # Notify user via Redis/Websockets
    await redis_client.publish(f"user_notifications_{transaction.wallet_id}", "Your transaction has been approved.")
    
    return {"status": "success", "message": "Order approved."}

@router.post("/orders/{order_id}/reject")
async def reject_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Rejects a pending transaction.
    CRITICAL: If it's a withdrawal, we MUST refund the locked amount back to the user's wallet.
    """
    query = select(LedgerTransaction).where(LedgerTransaction.id == order_id)
    result = await db.execute(query)
    transaction = result.scalar_one_or_none()

    if not transaction or transaction.status != "pending":
        raise HTTPException(status_code=400, detail="Invalid order.")

    transaction.status = "rejected"

    # Reverse the ledger math if it was a withdrawal
    if transaction.transaction_type == "withdrawal":
        wallet_query = select(Wallet).where(Wallet.id == transaction.wallet_id)
        wallet_result = await db.execute(wallet_query)
        wallet = wallet_result.scalar_one()
        # amount is stored as negative for withdrawals, so we subtract the negative (adds it back)
        wallet.cached_balance -= transaction.amount 

    await db.commit()
    return {"status": "success", "message": "Order rejected and funds reversed if applicable."}


# ---------------------------------------------------------
# 2. APP CONFIGURATION (PAYMENT METHODS & CURRENCIES)
# ---------------------------------------------------------

@router.get("/payment-methods")
async def get_payment_methods(db: AsyncSession = Depends(get_db)):
    """Fetches all payment gateways the platform supports."""
    query = select(PaymentMethod)
    result = await db.execute(query)
    return result.scalars().all()

@router.patch("/payment-methods/{method_id}")
async def toggle_payment_method(method_id: uuid.UUID, is_active: bool, db: AsyncSession = Depends(get_db)):
    """Turns a payment gateway on or off for the mobile app instantly."""
    await db.execute(
        update(PaymentMethod).where(PaymentMethod.id == method_id).values(is_active=is_active)
    )
    await db.commit()
    return {"status": "success"}

@router.patch("/currencies")
async def update_trading_currencies(currencies: list[str], db: AsyncSession = Depends(get_db)):
    """Updates the supported fiat/crypto pairs in the SiteSettings."""
    await db.execute(update(SiteSettings).values(supported_currencies=currencies))
    await db.commit()
    return {"status": "success", "supported_currencies": currencies}


# ---------------------------------------------------------
# 3. LIVE CHAT & SUPPORT (ADMIN SIDE)
# ---------------------------------------------------------

@router.get("/chat/active-sessions")
async def get_active_chats():
    """
    Fetches active support tickets/chats. 
    In a high-scale app, you might query Redis for active socket connections 
    or a 'SupportTicket' Postgres table.
    """
    # Placeholder: Retrieve active sessions from Redis or DB
    return {"active_sessions": []}

@router.post("/chat/reply/{user_id}")
async def admin_chat_reply(user_id: str, message: str):
    """
    Sends an admin reply directly into the user's live WebSocket stream via Redis.
    """
    payload = {"sender": "admin", "message": message, "timestamp": "now"}
    
    # Broadcast to the specific user's Redis channel
    await redis_client.publish(f"chat_stream_{user_id}", str(payload))
    return {"status": "message_sent"}


# ---------------------------------------------------------
# 4. PUSH NOTIFICATIONS
# ---------------------------------------------------------

@router.post("/notifications/broadcast")
async def broadcast_notification(title: str, body: str):
    """
    Pushes a system-wide alert (e.g., "Trading is down for maintenance") 
    to all active mobile app users via the global WebSocket channel.
    """
    payload = {"type": "system_alert", "title": title, "body": body}
    await redis_client.publish("dunex_global_stream", str(payload))
    return {"status": "broadcast_sent"}


# ---------------------------------------------------------
# 5. PLATFORM REPORTS & EXPORTS
# ---------------------------------------------------------

@router.get("/reports/volume")
async def get_trading_volume(days: int = 7, db: AsyncSession = Depends(get_db)):
    """
    Aggregates ledger data to build charts on the Next.js dashboard.
    """
    # Example logic to sum transaction amounts over the last X days.
    # For a real implementation, you would group by Date using Postgres DATE_TRUNC.
    query = select(func.sum(LedgerTransaction.amount)).where(
        LedgerTransaction.status == "completed",
        LedgerTransaction.amount > 0
    )
    result = await db.execute(query)
    total_volume = result.scalar() or 0.0
    
    return {"timeframe_days": days, "total_inflow_volume": total_volume}