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
