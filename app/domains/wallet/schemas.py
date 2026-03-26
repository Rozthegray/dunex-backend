from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class TransactionRequest(BaseModel):
    # Enforce strictly positive numbers at the API boundary
    amount: float = Field(..., gt=0, description="The amount must be greater than zero.")
    currency: str = Field(default="USD", max_length=3)
    payment_method_id: Optional[UUID] = None # Optional so the mobile app doesn't crash
    destination_details: Optional[str] = None # 🚨 ADD THIS

class TransactionResponse(BaseModel):
    status: str
    reference: str
    amount: float
    new_balance: float
    message: str