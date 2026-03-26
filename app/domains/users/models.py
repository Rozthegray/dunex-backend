import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class SiteSettings(Base):
    __tablename__ = "site_settings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Core Engines
    trading_enabled = Column(Boolean, default=True)
    withdrawals_enabled = Column(Boolean, default=True)
    deposits_enabled = Column(Boolean, default=True)  # 🚨 NEW
    
    # Defense Protocols
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(String, nullable=True)  # 🚨 NEW
    
    # Security & Limits
    kyc_required_for_withdrawal = Column(Boolean, default=False)  # 🚨 NEW
    min_withdrawal_usd = Column(String, default="50")  # 🚨 NEW
    max_withdrawal_usd = Column(String, default="100000")  # 🚨 NEW
    
    supported_currencies = Column(JSONB, default=["USD", "NGN", "BTC", "USDT"])
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) # 🚨 NEW

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
    ssn = Column(String, nullable=True)
    id_card_url = Column(String, nullable=True)
    govt_id_url = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    wallets = relationship("Wallet", back_populates="owner")