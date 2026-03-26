import asyncio
from app.db.session import engine
from app.domains.users.models import Base, User, SiteSettings
from app.domains.wallet.models import Wallet, LedgerTransaction, PaymentMethod
from app.domains.admin.models import AdminActivityLog

async def force_create_schema():
    print("Initiating direct connection to Neon PostgreSQL...")
    async with engine.begin() as conn:
        print("Wiping old tables...")
        # THIS is the crucial line that was missing! It deletes the outdated tables.
        await conn.run_sync(Base.metadata.drop_all)
        
        print("Building fresh database tables with new columns...")
        await conn.run_sync(Base.metadata.create_all)
        
    print("Schema creation complete! The database is ready.")

if __name__ == "__main__":
    asyncio.run(force_create_schema())