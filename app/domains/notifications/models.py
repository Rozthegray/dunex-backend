import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.domains.users.models import Base

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # Optional, links to the user if applicable
    type = Column(String, nullable=False)                # 'whatsapp', 'email', or 'push'
    status = Column(String, nullable=False)              # 'sent' or 'failed'
    payload = Column(JSONB, nullable=True)               # Stores the exact error or success response
    created_at = Column(DateTime, default=datetime.utcnow)