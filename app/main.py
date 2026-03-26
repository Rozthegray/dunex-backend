import os
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# 🚨 THE FIX: Import ALL models here so SQLAlchemy knows to create their tables
from app.db.session import engine
from app.domains.users.models import Base, User, SiteSettings
from app.domains.wallet.models import Wallet, PaymentMethod
from app.domains.chat.models import ChatMessage, SupportTicket

# ---> IMPORT ALL ROUTERS HERE <---
from app.domains.users.auth import router as auth_router
from app.domains.users.router import router as users_router # <--- Your new settings/KYC router
from app.domains.admin.router import router as admin_router
from app.domains.wallet.router import router as wallet_router
from app.domains.trade.router import router as trade_router 
from app.domains.chat.router import router as chat_router

# 1. Sentry Initialization
def custom_traces_sampler(sampling_context):
    asgi_scope = sampling_context.get("asgi_scope")
    if asgi_scope and asgi_scope.get("path") == "/api/health":
        return 0.0
    return 0.1

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN", ""),
    traces_sampler=custom_traces_sampler,
    profiles_sample_rate=0.1,
)

# 2. Asynchronous Lifespan Management (Auto-Creates Missing Tables!)
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("System Booting: Initializing secure connections...")
    
    # This will now detect User, Wallet, PaymentMethod, etc. and create them!
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database Tables Verified & Synced!")
        
    yield
    print("System Shutting Down: Closing database pools...")

# 3. FastAPI Initialization
app = FastAPI(
    title="Core Financial Engine",
    description="Async API handling ledgers, trading execution, and real-time chat.",
    version="1.0.0",
    lifespan=lifespan
)

# 4. Security: CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Keep-Alive / Health Endpoint
@app.get("/api/health", tags=["System Observability"])
async def health_check():
    return {
        "status": "operational", 
        "environment": os.getenv("ENVIRONMENT", "development")
    }

# 6. Router Inclusions
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/api/v1") # Includes the new /users endpoints
app.include_router(admin_router, prefix="/api/v1")
app.include_router(wallet_router, prefix="/api/v1/wallet") 
app.include_router(trade_router, prefix="/api/v1") 
app.include_router(chat_router, prefix="/api/v1")

# 7. Static Files Mount (Required for image uploads)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")