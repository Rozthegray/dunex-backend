import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.domains.wallet.models import Wallet, LedgerTransaction

async def execute_trade_settlement(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    amount_usd: float, 
    trade_type: str, # e.g., 'TRADE_OPEN_DEBIT' or 'TRADE_CLOSE_CREDIT'
    reference: str
):
    """
    Adjusts the main USD wallet for trading activity.
    Negative amounts deduct (buying/opening trade).
    Positive amounts credit (selling/winning trade).
    """
    # 1. Locate the user's wallet and lock the row to prevent race conditions
    query = select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    # 2. Check for sufficient funds if it's a deduction (amount_usd is negative)
    if amount_usd < 0 and wallet.cached_balance < abs(amount_usd):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Insufficient USD balance to execute trade."
        )

    # 3. Create the immutable ledger record for the trade
    transaction = LedgerTransaction(
        wallet_id=wallet.id,
        amount=amount_usd, 
        transaction_type="trade_settlement",
        status="completed", # Trades settle instantly
        reference=reference,
        destination_details=trade_type 
    )
    db.add(transaction)

    # 4. Physically alter the wallet balance
    wallet.cached_balance += amount_usd

    # 5. Commit the block
    await db.commit()
    await db.refresh(wallet)
    
    return wallet.cached_balance

async def execute_deposit(
    db: AsyncSession, 
    wallet_id: uuid.UUID, 
    amount: float, 
    reference: str,
    payment_method: str = None,
    receipt_url: str = None
):
    """
    Registers a deposit request. Funds are held in a pending state 
    until an administrator verifies and clears the transaction.
    """
    if amount <= 0:
        raise ValueError("Deposit amount must be strictly positive.")

    # 1. Verify the wallet exists
    query = select(Wallet).where(Wallet.id == wallet_id)
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    # 2. Create the immutable ledger record (Credit)
    transaction = LedgerTransaction(
        wallet_id=wallet_id,
        amount=amount,  # Positive amount for deposits
        transaction_type="deposit",
        status="pending",  # Strict pending lock
        reference=reference,
        # Uncomment these if you added them to your LedgerTransaction model
        # payment_method=payment_method,
        # receipt_url=receipt_url
    )
    db.add(transaction)

    # 3. Commit the transaction block (Balance remains unchanged until admin approval)
    await db.commit()
    await db.refresh(transaction)
    
    return transaction

async def execute_withdrawal(
    db: AsyncSession, 
    wallet_id: uuid.UUID, 
    amount: float, 
    reference: str,
    destination_details: str = None # 🚨 1. NEW: Accept the destination details
):
    """
    Executes a withdrawal with a strict row-level lock to prevent race conditions.
    """
    if amount <= 0:
        raise ValueError("Withdrawal amount must be strictly positive.")

    # 1. Lock the wallet row for this specific transaction
    query = select(Wallet).where(Wallet.id == wallet_id).with_for_update()
    result = await db.execute(query)
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    if wallet.cached_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Insufficient funds."
        )

    # 2. Create the immutable ledger record (Debit)
    transaction = LedgerTransaction(
        wallet_id=wallet_id,
        amount=-amount, 
        transaction_type="withdrawal",
        status="pending", 
        reference=reference,
        destination_details=destination_details # 🚨 2. NEW: Save it to the database!
    )
    db.add(transaction)

    # 3. Deduct immediately to prevent double-spending while pending
    wallet.cached_balance -= amount

    # 4. Commit the transaction block
    await db.commit()
    return transaction
