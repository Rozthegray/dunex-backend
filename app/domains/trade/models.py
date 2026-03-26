import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.domains.users.models import Base

class SubWallet(Base):
    __tablename__ = "sub_wallets"


    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String, index=True, nullable=False) # e.g., "BTC", "ETH"
    balance = Column(Float, default=0.0, nullable=False)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class TradeExecution(Base):
    """Logs every buy/sell order the user makes."""
    __tablename__ = "trade_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pair = Column(String, nullable=False) # e.g., "BTC/USD"
    trade_type = Column(String, nullable=False) # "BUY" or "SELL"
    
    amount_usd = Column(Float, nullable=False) # How much USD they spent/received
    amount_crypto = Column(Float, nullable=False) # How much Crypto they got/sold
    entry_price = Column(Float, nullable=False) # The price of the coin at execution
    
    status = Column(String, default="completed") # "completed", "failed"
    created_at = Column(DateTime(timezone=True), server_default=func.now())