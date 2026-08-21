from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_tenant
from app.models import Widget, Tenant
from app.schemas import WidgetCreate, WidgetUpdate, WidgetOut

router = APIRouter(prefix="/api/widgets", tags=["widgets"])


def _to_out(widget: Widget, base_url: str = "http://localhost:8000") -> WidgetOut:
    snippet = f'<script src="{base_url}/widget.js?id={widget.id}"></script>'
    return WidgetOut(
        id=widget.id,
        title=widget.title,
        description=widget.description,
        button_text=widget.button_text,
        version=widget.version,
        embed_snippet=snippet,
    )


@router.post("", response_model=WidgetOut, status_code=201)
def create_widget(
    payload: WidgetCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widget = Widget(
        tenant_id=tenant.id,
        title=payload.title,
        description=payload.description,
        button_text=payload.button_text,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return _to_out(widget)


@router.get("", response_model=list[WidgetOut])
def list_widgets(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widgets = db.query(Widget).filter(Widget.tenant_id == tenant.id).all()
    return [_to_out(w) for w in widgets]


def _get_owned_widget(widget_id: str, tenant: Tenant, db: Session) -> Widget:
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    # tenant isolation: a widget that exists but isn't yours is invisible, not a 403 leak
    if widget.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget


@router.get("/{widget_id}", response_model=WidgetOut)
def get_widget(
    widget_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widget = _get_owned_widget(widget_id, tenant, db)
    return _to_out(widget)


@router.patch("/{widget_id}", response_model=WidgetOut)
def update_widget(
    widget_id: str,
    payload: WidgetUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widget = _get_owned_widget(widget_id, tenant, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(widget, field, value)
    widget.version += 1  # bump version -> busts the cached bundle/config
    db.commit()
    db.refresh(widget)
    return _to_out(widget)


@router.delete("/{widget_id}", status_code=204)
def delete_widget(
    widget_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widget = _get_owned_widget(widget_id, tenant, db)
    db.delete(widget)
    db.commit()
