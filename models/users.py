from enum import Enum
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class CredentialStatus(str, Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class Token(BaseModel):
    access_token: str
    token_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TokenData(BaseModel):
    email: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    email: str | None = None
    full_name: str | None = None
    disabled: bool = True
    password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserInDB(User):
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class OTP(BaseModel):
    email: EmailStr
    otp: int
    verify: bool = False
    expire: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)



class APICredential(BaseModel):
    user : User
    app_key: str
    secret_key: str
    status: CredentialStatus = CredentialStatus.active
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)