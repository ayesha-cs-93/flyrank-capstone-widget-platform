from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Widget, Submission
from app.schemas import SubmissionCreate
from app.services.geo import enrich_ip
from app.services.notify import send_confirmation, NotifyError
from app.config import settings

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

limiter = Limiter(key_func=get_remote_address)

MAX_BODY_BYTES = 10_000  # oversized payload guard


@router.post("", status_code=201)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def create_submission(
    request: Request,
    response: Response,
    payload: SubmissionCreate,
    db: Session = Depends(get_db),
):
    # oversized payload check (Content-Length header, cheap check before any work)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    widget = db.query(Widget).filter(Widget.id == payload.widget_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    # CORS: submission endpoint accepts any origin (that's the point -- customer
    # sites are on origins we don't control). Preflight OPTIONS is handled by
    # the CORSMiddleware configured in main.py.
    response.headers["Access-Control-Allow-Origin"] = "*"

    # --- spam check: honeypot ---
    # Real visitors never see or fill this field (hidden via CSS in widget.js).
    # A filled honeypot means a bot filled every field it could find.
    if payload.honeypot:
        # Return a fake success so bots don't learn the check exists.
        # Nothing is stored.
        return {"status": "ok"}

    ip = get_remote_address(request)

    # --- enrichment: provider A -> provider B -> none. Must never raise. ---
    geo = await enrich_ip(ip)

    submission = Submission(
        widget_id=widget.id,
        tenant_id=widget.tenant_id,
        name=payload.name,
        email=payload.email,
        message=payload.message,
        ip_address=ip,
        country=geo["country"],
        city=geo["city"],
        geo_provider_used=geo["provider_used"],
        spam_flagged=False,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # --- safe side effect: confirmation email ---
    # Failure here must NEVER break the response -- the submission is already
    # stored and committed above. This is the "degrade, don't fail" pattern.
    try:
        send_confirmation(payload.email, widget.title)
    except NotifyError:
        pass  # logged inside notify.py; submission still succeeds

    return {"status": "ok", "id": submission.id}
