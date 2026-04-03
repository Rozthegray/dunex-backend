import os
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 🚨 Database & Models
from app.db.session import engine
from app.domains.users.models import Base, User, SiteSettings
from app.domains.wallet.models import Wallet, PaymentMethod
from app.domains.chat.models import ChatMessage, SupportTicket

# ---> ROUTERS <---
from app.domains.users.auth import router as auth_router
from app.domains.users.router import router as users_router
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

# 2. Asynchronous Lifespan Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("System Booting: Initializing secure connections...")
    yield
    print("System Shutting Down: Closing database pools...")

# 3. FastAPI Initialization
app = FastAPI(
    title="Dunex Core Financial Engine",
    description="Async API handling ledgers, trading execution, and real-time chat.",
    version="1.0.0",
    lifespan=lifespan
)

# 4. Security: CORS Middleware (Hardened for Production)
ALLOWED_ORIGINS = [
    "http://localhost:3000",          # Next.js Local
    "http://localhost:8081",          # Expo Local Web
    "https://admin.dunexmarkets.com", 
    "https://app.dunexmarkets.com",   
    "https://www.dunexmarkets.com",   # Production with www
    "https://dunexmarkets.com",       # Production root
    "https://dunex-frontend.vercel.app", # Vercel fallback
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS, 
    allow_credentials=True,
    allow_methods=["*"],              # 🚨 Changed to allow all to prevent preflight fails
    allow_headers=["*"],
)

# 5. Keep-Alive / Health Endpoint
@app.get("/api/health", tags=["System Observability"])
async def health_check():
    return {
        "status": "operational", 
        "environment": os.getenv("ENVIRONMENT", "production")
    }

# 6. Router Inclusions
# Note: Ensure these prefixes match what your frontend calls!
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/api/v1") 
app.include_router(admin_router, prefix="/api/v1")
app.include_router(wallet_router, prefix="/api/v1/wallet") 
app.include_router(trade_router, prefix="/api/v1") 
app.include_router(chat_router, prefix="/api/v1")
