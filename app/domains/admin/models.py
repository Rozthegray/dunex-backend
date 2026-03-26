import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.domains.users.models import Base

class AdminActivityLog(Base):
    __tablename__ = "admin_activity_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False) # e.g., "UPDATED_SETTINGS", "APPROVED_KYC"
    target_entity = Column(String, nullable=True) # e.g., "SiteSettings", "User:1234"
    details = Column(JSONB, nullable=True) # Stores the exact payload of the change
    created_at = Column(DateTime, default=datetime.utcnow)