import asyncio
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.core.security import get_password_hash
from app.domains.users.models import User

# CRITICAL FIX: We must import the wallet models so SQLAlchemy 
# registers the "Wallet" class in its metadata before executing.
from app.domains.wallet.models import Wallet, LedgerTransaction, PaymentMethod

async def create_superadmin():
    async with AsyncSessionLocal() as db:
        admin_email = "adminmaster@dunexmarkets.com"
        
        # Check if the admin already exists
        query = select(User).where(User.email == admin_email)
        result = await db.execute(query)
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print(f"Admin {admin_email} already exists.")
            return

        # Cryptographically hash the password before inserting
        hashed_pw = get_password_hash("DunexMasterBABA2020SIX!")
        
        # Create the user with the strict 'superadmin' role
        superadmin = User(
            email=admin_email,
            hashed_password=hashed_pw,
            full_name="Chief Administrator",
            role="superadmin",
            is_active=True,
            kyc_status="verified"
        )
        
        db.add(superadmin)
        await db.commit()
        print(f"Master Admin created successfully: {admin_email}")

if __name__ == "__main__":
    asyncio.run(create_superadmin())