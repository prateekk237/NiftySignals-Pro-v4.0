"""
API Key model — stores NVIDIA NIM and OpenAI keys in SQLite.
Supports multiple keys per provider with priority ordering and fallback.
"""

from sqlalchemy import Column, Integer, Text, Float, Boolean
from core.database import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(Text, nullable=False)          # "nvidia_nim" | "openai" | "openai_compatible"
    label = Column(Text, nullable=False)             # User-friendly name: "My NIM Key", "OpenAI Main"
    api_key = Column(Text, nullable=False)           # The actual key (stored encrypted in prod)
    base_url = Column(Text, nullable=True)           # Custom base URL (for NIM, local LLMs, etc.)
    model = Column(Text, nullable=True)              # Override model: "gpt-4o", "llama-3.3-70b" etc.
    priority = Column(Integer, nullable=False, default=1)  # Lower = tried first. 1=primary, 2=fallback, etc.
    is_active = Column(Boolean, nullable=False, default=True)
    rate_limit_rpm = Column(Integer, nullable=True, default=40)  # Requests per minute
    total_calls = Column(Integer, nullable=False, default=0)
    total_errors = Column(Integer, nullable=False, default=0)
    last_used_at = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=True)
