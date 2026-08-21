from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, constr


# ---------- Widgets ----------

class WidgetCreate(BaseModel):
    title: constr(min_length=1, max_length=120)
    description: Optional[constr(max_length=500)] = None
    button_text: constr(min_length=1, max_length=40) = "Submit"


class WidgetUpdate(BaseModel):
    title: Optional[constr(min_length=1, max_length=120)] = None
    description: Optional[constr(max_length=500)] = None
    button_text: Optional[constr(min_length=1, max_length=40)] = None


class WidgetOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    button_text: str
    version: int
    embed_snippet: str

    class Config:
        from_attributes = True


class WidgetConfigOut(BaseModel):
    title: str
    description: Optional[str]
    button_text: str


# ---------- Submissions ----------

class SubmissionCreate(BaseModel):
    widget_id: str
    name: constr(min_length=1, max_length=120)
    email: EmailStr
    message: Optional[constr(max_length=2000)] = None
    # honeypot: real visitors never fill this (hidden via CSS in the widget).
    # Any non-empty value here means a bot filled it -> silently drop.
    honeypot: Optional[constr(max_length=200)] = Field(default="", max_length=200)


class SubmissionOut(BaseModel):
    id: str
    name: str
    email: str
    message: Optional[str]
    country: Optional[str]
    city: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total_submissions: int
    submissions_by_day: dict
    top_countries: dict
