from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str

class UserResponse(BaseModel):
    """🛑 CRITICAL: This schema ensures the 'id' is sent to the mobile app."""
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    kyc_status: str

    class Config:
        from_attributes = True

class PasswordRecoveryRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    email: str
    code: str
    new_password: str