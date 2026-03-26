import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import NullPool
from dotenv import load_dotenv

load_dotenv()

# CRITICAL: This must be your Neon POOLED connection string (ep-[id]-pooler.neon.tech)
# Do not use the direct connection string here.
DATABASE_URL = os.getenv("NEON_DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("NEON_DATABASE_URL environment variable is not set.")

# We use NullPool here to explicitly prevent SQLAlchemy from holding onto connections.
# PgBouncer handles the transaction pooling on the Neon server side.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool, 
)

AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_db():
    """
    Dependency to be injected into FastAPI routes.
    Yields a database session and ensures it closes immediately after the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()