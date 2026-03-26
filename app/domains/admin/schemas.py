from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class OverviewStats(BaseModel):
    total_users: int
    pending_kyc: int
    total_platform_volume: float
    active_orders: int

class UserAdminView(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str]
    kyc_status: str
    cached_balance: float
    joined_at: datetime

class SiteSettingsUpdate(BaseModel):
    trading_enabled: Optional[bool] = None
    withdrawals_enabled: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    supported_currencies: Optional[List[str]] = None

class AdminActivityResponse(BaseModel):
    id: UUID
    admin_id: UUID
    action: str
    target_entity: Optional[str]
    details: Optional[Dict[str, Any]]
    created_at: datetime