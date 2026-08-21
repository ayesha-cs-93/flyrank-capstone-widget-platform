import hashlib

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def get_current_tenant(
    x_api_key: str = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    tenant = db.query(Tenant).filter(Tenant.api_key_hash == hash_key(x_api_key)).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant
