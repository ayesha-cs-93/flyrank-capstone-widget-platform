from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_tenant
from app.models import Widget, Submission, Tenant
from app.schemas import SubmissionOut, StatsOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _widget_scope(widget_id: str | None, tenant: Tenant, db: Session):
    """Every dashboard query is scoped to the caller's tenant. If a widget_id
    is given, verify it belongs to this tenant before using it as a filter."""
    query = db.query(Submission).filter(Submission.tenant_id == tenant.id)
    if widget_id:
        widget = db.query(Widget).filter(Widget.id == widget_id, Widget.tenant_id == tenant.id).first()
        if not widget:
            raise HTTPException(status_code=404, detail="Widget not found")
        query = query.filter(Submission.widget_id == widget_id)
    return query


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    widget_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = _widget_scope(widget_id, tenant, db)
    rows = query.order_by(Submission.created_at.desc()).offset(offset).limit(limit).all()
    return rows


@router.get("/stats", response_model=StatsOut)
def get_stats(
    widget_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = _widget_scope(widget_id, tenant, db)
    rows = query.all()

    by_day = defaultdict(int)
    by_country = defaultdict(int)
    for r in rows:
        day = r.created_at.strftime("%Y-%m-%d")
        by_day[day] += 1
        if r.country:
            by_country[r.country] += 1

    return StatsOut(
        total_submissions=len(rows),
        submissions_by_day=dict(by_day),
        top_countries=dict(sorted(by_country.items(), key=lambda x: -x[1])[:10]),
    )
