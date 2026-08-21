from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import Base, engine
from app.routers import widgets, delivery, submissions, dashboard
from app.routers.submissions import limiter

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: the submission + config + widget.js endpoints must accept requests
# from origins we don't control (that's the entire point of this capstone).
# Widget management (/api/widgets) is also under this policy but is protected
# by the X-API-Key auth layer, not CORS -- CORS is not an auth mechanism.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # never leak a raw 500 with a stack trace to the public internet
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(widgets.router)
app.include_router(delivery.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)


@app.get("/health")
def health():
    return {"status": "ok"}
