import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.domains.wallet.models import PaymentMethod

async def seed_payments():
    # Use the new Asynchronous session context
    async with AsyncSessionLocal() as session:
        
        # 1. Safety check to prevent duplicates
        result = await session.execute(select(PaymentMethod).limit(1))
        if result.scalar_one_or_none():
            print("⚠️ Payment methods already exist in the database. Skipping seed.")
            return

        print("🚀 Seeding Upgraded Payment Methods...")
        
        # 2. Define the upgraded payment methods
        methods = [
            {
                "name": "USDT (TRC20)",
                "details": "Network: TRON (TRC20)\nAddress: TQxxxxxxxYourAddressHerexxxxxxx",
                "instructions": "Transfer USDT via TRC20 network and upload the transaction screenshot."
            },
            {
                "name": "Bitcoin (BTC)",
                "details": "Network: Bitcoin\nAddress: bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfJH7V",
                "instructions": "Send BTC to the address above. Upload the transaction hash or screenshot."
            },
            {
                "name": "Local Bank Transfer",
                "details": "Bank: Zenith Bank\nAccount Name: Dunex Markets\nAccount No: 1234567890",
                "instructions": "Use your registered name in the transfer narration. Upload the payment receipt."
            }
        ]

        # 3. Add them to the database
        for m in methods:
            new_method = PaymentMethod(
                name=m["name"],
                details=m["details"],
                instructions=m["instructions"],
                is_active=True
            )
            session.add(new_method)
        
        # 4. Commit the transaction asynchronously
        await session.commit()
        print("✅ Upgraded Payment methods seeded successfully!")

if __name__ == "__main__":
    # Run the async function using asyncio
    asyncio.run(seed_payments())