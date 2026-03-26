import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

# Make sure this points to your Base!
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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    currency = Column(String, nullable=False, default="USD")
    cached_balance = Column(Float, default=0.0) 
    
    owner = relationship("User", back_populates="wallets")
    transactions = relationship("LedgerTransaction", back_populates="wallet")

class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    
    amount = Column(Float, nullable=False)
    transaction_type = Column(String, nullable=False) 
    status = Column(String, default="pending") 
    reference = Column(String, unique=True, nullable=False) 
    
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"), nullable=True)
    proof_url = Column(String, nullable=True) 
    
    # 🚨 ADD THIS NEW COLUMN:
    destination_details = Column(String, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)
    wallet = relationship("Wallet", back_populates="transactions")