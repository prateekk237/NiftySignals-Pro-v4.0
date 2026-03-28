"""
Pydantic schemas for API key management.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class APIKeyCreate(BaseModel):
    provider: str = Field(..., description="nvidia_nim | openai | openai_compatible")
    label: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=5)
    base_url: Optional[str] = None
    model: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=10)
    is_active: bool = True
    rate_limit_rpm: Optional[int] = Field(default=40, ge=1, le=10000)
    notes: Optional[str] = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        valid = {"nvidia_nim", "openai", "openai_compatible"}
        if v not in valid:
            raise ValueError(f"provider must be one of {valid}")
        return v


class APIKeyUpdate(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    is_active: Optional[bool] = None
    rate_limit_rpm: Optional[int] = None
    notes: Optional[str] = None


class APIKeyResponse(BaseModel):
    id: int
    provider: str
    label: str
    api_key_masked: str  # Only show last 4 chars
    base_url: Optional[str] = None
    model: Optional[str] = None
    priority: int
    is_active: bool
    rate_limit_rpm: Optional[int] = None
    total_calls: int
    total_errors: int
    last_used_at: Optional[str] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class APIKeyTestResult(BaseModel):
    success: bool
    provider: str
    model_used: str = ""
    response_preview: str = ""
    latency_ms: int = 0
    error: str = ""
