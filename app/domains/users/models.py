import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class SiteSettings(Base):
    __tablename__ = "site_settings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Core Engines
    trading_enabled = Column(Boolean, default=True)
    withdrawals_enabled = Column(Boolean, default=True)
    deposits_enabled = Column(Boolean, default=True)  
    
    # Defense Protocols
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(String, nullable=True)  
    
    # Security & Limits
    kyc_required_for_withdrawal = Column(Boolean, default=False)  
    min_withdrawal_usd = Column(String, default="50")  
    max_withdrawal_usd = Column(String, default="100000")  
    
    supported_currencies = Column(JSONB, default=["USD", "NGN", "BTC", "USDT"])
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    role = Column(String, default="user", nullable=False) 
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    base_currency = Column(String, default="USD")
    
    # --- New KYC Fields ---
    kyc_status = Column(String, default="unverified")
    dob = Column(String, nullable=True)
    id_card_url = Column(String, nullable=True)
    govt_id_url = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    country = Column(String, nullable=True)
    id_number = Column(String, nullable=True) # Replaces the old 'ssn'

    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # 🚨 NEW: AFFILIATE REFERRAL ENGINE FIELDS 🚨
    referral_code = Column(String(50), unique=True, index=True, nullable=True)
    referred_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # ---------------------------------------------------------
    # Relationships
# ---------------------------------------------------------
    # 🚨 ADDED CASCADE HERE
    wallets = relationship("Wallet", back_populates="owner", cascade="all, delete-orphan")
    
    # Self-referential relationship so a User can "own" other Users in the tree
    referred_by = relationship("User", remote_side=[id], backref="referrals")

    # 🚨 ADDED CASCADE HERE
    payout_accounts = relationship("UserPayoutAccount", back_populates="owner", cascade="all, delete-orphan") 


class UserPayoutAccount(Base):
    __tablename__ = "user_payout_accounts"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type       = Column(String(20), nullable=False)   # 'bank' | 'crypto'
    label      = Column(String(120), nullable=False)  # "Chase Checking", "BTC Wallet"
    details    = Column(String(255), nullable=False)  # account number or wallet address
    created_at = Column(DateTime, default=datetime.utcnow)

    # 🚨 REMOVED THE SNEAKY TRAILING COMMA HERE
    owner = relationship("User", back_populates="payout_accounts")
