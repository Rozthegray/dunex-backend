import os
import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse

# Load variables from .env file
load_dotenv()

# 1. Grab the URL
DATABASE_URL = os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Database URL is missing. Please add NEON_DATABASE_URL to your .env file.")

# 2. Fix the URL Driver to force Asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 3. Handle the Asyncpg 'sslmode' Bug
# If the URL has ?sslmode=require, we must strip it out and pass it via connect_args
connect_args = {}

if "?sslmode=" in DATABASE_URL:
    # Remove the query parameter from the URL string
    parsed_url = urlparse(DATABASE_URL)
    DATABASE_URL = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, '', parsed_url.fragment))
    
    # Define an SSL context that Asyncpg understands
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connect_args["ssl"] = ssl_context

# 4. Create the Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False, 
    connect_args=connect_args # Pass the fixed SSL context here!
)

# 5. Create the Session Maker
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# 6. Dependency injection for your routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session