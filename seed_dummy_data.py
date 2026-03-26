import asyncio
import random
import uuid
from datetime import datetime, timedelta

from app.db.session import AsyncSessionLocal
from app.core.security import get_password_hash
from app.domains.users.models import User
from app.domains.wallet.models import Wallet, LedgerTransaction

async def generate_dummy_data():
    print("Initiating connection to Neon PostgreSQL...")
    
    async with AsyncSessionLocal() as db:
        print("Generating 50 synthetic users, wallets, and ledger histories...")
        
        first_names = ["James", "Sarah", "Michael", "Emma", "David", "Oluwaseun", "Chidi", "Aisha", "John", "Grace"]
        last_names = ["Smith", "Johnson", "Williams", "Okafor", "Adeyemi", "Brown", "Jones", "Garcia", "Davis", "Chen"]
        statuses = ["verified", "verified", "pending", "unverified"] # Weighted toward verified

        # Hash a generic password once to save time
        hashed_pw = get_password_hash("TestUser2026!")

        users_created = 0
        transactions_created = 0

        for _ in range(50):
            # 1. Create User
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            email = f"{fname.lower()}.{lname.lower()}{random.randint(100,9999)}@example.com"
            
            # Randomize join date within the last 60 days
            join_date = datetime.utcnow() - timedelta(days=random.randint(1, 60))

            user = User(
                email=email,
                hashed_password=hashed_pw,
                full_name=f"{fname} {lname}",
                kyc_status=random.choice(statuses),
                role="user",
                created_at=join_date
            )
            db.add(user)
            await db.flush() # Flush to assign the UUID so we can link the wallet

            # 2. Create Wallet
            wallet = Wallet(
                user_id=user.id,
                currency="USD",
                cached_balance=0.0
            )
            db.add(wallet)
            await db.flush()

            # 3. Create Transactions
            num_txs = random.randint(0, 8)
            current_balance = 0.0

            for _ in range(num_txs):
                tx_type = random.choice(["deposit", "withdrawal", "trade_buy", "trade_sell"])
                amount = round(random.uniform(50.0, 5000.0), 2)

                # Deduct funds for withdrawals and buys
                if tx_type in ["withdrawal", "trade_buy"]:
                    amount = -amount
                    
                    # Prevent massive negative balances for realism
                    if current_balance + amount < 0:
                        tx_type = "deposit"
                        amount = abs(amount)

                current_balance += amount
                
                # Randomize transaction date after the user joined
                tx_date = join_date + timedelta(days=random.randint(0, (datetime.utcnow() - join_date).days))

                tx = LedgerTransaction(
                    wallet_id=wallet.id,
                    amount=amount,
                    transaction_type=tx_type,
                    status=random.choice(["completed", "completed", "completed", "pending", "failed"]),
                    reference=f"TXN-{uuid.uuid4().hex[:10].upper()}",
                    created_at=tx_date
                )
                db.add(tx)
                transactions_created += 1

            # 4. Update the wallet's cached balance
            wallet.cached_balance = round(current_balance, 2)
            users_created += 1

        print("Writing synthetic data to the database...")
        await db.commit()
        
        print("=========================================")
        print(f"SUCCESS: Injected {users_created} users and {transactions_created} ledger transactions.")
        print("=========================================")

if __name__ == "__main__":
    asyncio.run(generate_dummy_data())