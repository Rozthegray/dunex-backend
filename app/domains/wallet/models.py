import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.domains.users.models import Base

class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    method_type = Column(String, nullable=False) 
    account_details = Column(String, nullable=False) 
    instructions = Column(Text, nullable=True) 
    is_active = Column(Boolean, default=True)

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    currency = Column(String, nullable=False, default="USD")
    
    # 🚨 THE NEW 4-BALANCE LEDGER
    main_balance = Column(Float, default=0.0) 
    profit_balance = Column(Float, default=0.0) 
    bonus_balance = Column(Float, default=0.0) 
    referral_balance = Column(Float, default=0.0) 
    
    owner = relationship("User", back_populates="wallets")
    
    # 🚨 ADDED CASCADE HERE
    transactions = relationship("LedgerTransaction", back_populates="wallet", cascade="all, delete-orphan")

class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    
    amount = Column(Float, nullable=False)
    transaction_type = Column(String, nullable=False) # 'deposit' | 'withdrawal'
    
    # 🚨 ADD THIS: Tracks which of the 4 wallets this hit
    wallet_type = Column(String, default="main") # 'main' | 'profit' | 'bonus' | 'referral'
    
    status = Column(String, default="pending") 
    reference = Column(String, unique=True, nullable=False) 
    
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"), nullable=True)
    proof_url = Column(String, nullable=True) 
    destination_details = Column(String, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)
    wallet = relationship("Wallet", back_populates="transactions")
