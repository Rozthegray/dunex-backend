import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.domains.wallet.models import Wallet, LedgerTransaction

async def execute_deposit(
    db: AsyncSession, 
    wallet_id: uuid.UUID, 
    amount: float, 
    reference: str,
    payment_method_id: str = None,
    proof_image_url: str = None
):
    """Registers a deposit request. Funds are held in pending state."""
    if amount <= 0:
        raise ValueError("Deposit amount must be strictly positive.")

    query = select(Wallet).where(Wallet.id == wallet_id)
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    transaction = LedgerTransaction(
        wallet_id=wallet_id,
        amount=amount, 
        transaction_type="deposit",
        wallet_type="main", 
        status="pending",  
        reference=reference,
        proof_url=proof_image_url, 
        destination_details=f"Method ID: {payment_method_id}" if payment_method_id else None
    )
    db.add(transaction)

    await db.commit()
    await db.refresh(transaction)
    return transaction


async def execute_withdrawal(
    db: AsyncSession, 
    wallet_id: uuid.UUID, 
    amount: float, 
    reference: str,
    destination_details: str = None 
):
    """Executes an omni-withdrawal that pools liquidity from all 4 sub-wallets."""
    if amount <= 0:
        raise ValueError("Withdrawal amount must be strictly positive.")

    # 1. Lock the wallet row for this specific transaction
    query = select(Wallet).where(Wallet.id == wallet_id).with_for_update()
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    # 🚨 THE FIX: Calculate Total Equity across the entire ledger
    total_equity = (
        (wallet.main_balance or 0.0) + 
        (wallet.profit_balance or 0.0) + 
        (wallet.bonus_balance or 0.0) + 
        (wallet.referral_balance or 0.0)
    )

    if total_equity < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Insufficient funds. Total available equity is ${total_equity:.2f}."
        )

    # 2. Create the immutable ledger record
    transaction = LedgerTransaction(
        wallet_id=wallet_id,
        amount=-amount, 
        transaction_type="withdrawal",
        wallet_type="main", # Records as a general withdrawal on the main ledger
        status="pending", 
        reference=reference,
        destination_details=destination_details 
    )
    db.add(transaction)
    
    # 🚨 THE FIX: Cascade the deduction progressively across all wallets
    remaining_to_deduct = amount
    for field in ("main_balance", "profit_balance", "bonus_balance", "referral_balance"):
        if remaining_to_deduct <= 0:
            break
        
        current_val = getattr(wallet, field) or 0.0
        if current_val > 0:
            deduction = min(current_val, remaining_to_deduct)
            setattr(wallet, field, current_val - deduction)
            remaining_to_deduct -= deduction

    # 4. Commit the transaction block
    await db.commit()
    return transaction