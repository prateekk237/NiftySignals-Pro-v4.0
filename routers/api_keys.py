"""
API Key management endpoints — CRUD + test + reload.
Supports NVIDIA NIM, OpenAI, and any OpenAI-compatible provider.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import pytz

from core.database import get_db
from models.api_key import APIKey
from schemas.api_key import APIKeyCreate, APIKeyUpdate, APIKeyResponse, APIKeyTestResult
from services.llm_service import llm_service

router = APIRouter(prefix="/api/keys", tags=["api_keys"])
IST = pytz.timezone("Asia/Kolkata")


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****" + key[-4:] if len(key) > 4 else "****"
    return key[:4] + "..." + key[-4:]


def _to_response(k: APIKey) -> dict:
    return {
        "id": k.id, "provider": k.provider, "label": k.label,
        "api_key_masked": _mask_key(k.api_key),
        "base_url": k.base_url, "model": k.model, "priority": k.priority,
        "is_active": k.is_active, "rate_limit_rpm": k.rate_limit_rpm,
        "total_calls": k.total_calls, "total_errors": k.total_errors,
        "last_used_at": k.last_used_at, "last_error": k.last_error,
        "notes": k.notes, "created_at": k.created_at, "updated_at": k.updated_at,
    }


@router.get("", response_model=List[APIKeyResponse])
async def list_keys(
    provider: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all API keys (keys are masked)."""
    q = db.query(APIKey)
    if provider:
        q = q.filter(APIKey.provider == provider)
    keys = q.order_by(APIKey.priority.asc(), APIKey.id.asc()).all()
    return [_to_response(k) for k in keys]


@router.post("", response_model=APIKeyResponse, status_code=201)
async def create_key(data: APIKeyCreate, db: Session = Depends(get_db)):
    """Add a new API key. Saved permanently in SQLite."""
    now = datetime.now(pytz.utc).isoformat()
    k = APIKey(
        provider=data.provider, label=data.label, api_key=data.api_key,
        base_url=data.base_url, model=data.model, priority=data.priority,
        is_active=data.is_active, rate_limit_rpm=data.rate_limit_rpm,
        notes=data.notes, created_at=now, total_calls=0, total_errors=0,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    llm_service.reload_keys()
    return _to_response(k)


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_key(key_id: int, db: Session = Depends(get_db)):
    k = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not k:
        raise HTTPException(404, f"Key {key_id} not found")
    return _to_response(k)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_key(key_id: int, data: APIKeyUpdate, db: Session = Depends(get_db)):
    """Update an API key. Can change key, model, priority, active status."""
    k = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not k:
        raise HTTPException(404, f"Key {key_id} not found")

    if data.label is not None: k.label = data.label
    if data.api_key is not None: k.api_key = data.api_key
    if data.base_url is not None: k.base_url = data.base_url
    if data.model is not None: k.model = data.model
    if data.priority is not None: k.priority = data.priority
    if data.is_active is not None: k.is_active = data.is_active
    if data.rate_limit_rpm is not None: k.rate_limit_rpm = data.rate_limit_rpm
    if data.notes is not None: k.notes = data.notes
    k.updated_at = datetime.now(pytz.utc).isoformat()

    db.commit()
    db.refresh(k)
    llm_service.reload_keys()
    return _to_response(k)


@router.delete("/{key_id}")
async def delete_key(key_id: int, db: Session = Depends(get_db)):
    """Permanently delete an API key."""
    k = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not k:
        raise HTTPException(404, f"Key {key_id} not found")
    db.delete(k)
    db.commit()
    llm_service.reload_keys()
    return {"deleted": key_id, "label": k.label}


@router.post("/test", response_model=APIKeyTestResult)
async def test_key(data: APIKeyCreate):
    """Test an API key without saving it. Returns success + latency."""
    result = llm_service.test_key(
        provider=data.provider, api_key=data.api_key,
        base_url=data.base_url, model=data.model,
    )
    return result


@router.post("/{key_id}/test", response_model=APIKeyTestResult)
async def test_existing_key(key_id: int, db: Session = Depends(get_db)):
    """Test an existing saved key."""
    k = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not k:
        raise HTTPException(404, f"Key {key_id} not found")
    result = llm_service.test_key(
        provider=k.provider, api_key=k.api_key,
        base_url=k.base_url, model=k.model,
    )
    return result


@router.post("/reload")
async def reload_keys():
    """Force reload all keys from DB into the LLM service."""
    llm_service.reload_keys()
    return {"status": "reloaded", "providers": llm_service.providers}


@router.get("/status/providers")
async def get_providers():
    """Get status of all loaded LLM providers."""
    return {
        "available": llm_service.available,
        "providers": llm_service.providers,
    }
