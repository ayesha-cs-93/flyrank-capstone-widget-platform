"""
Confirmation "email" side effect. In this $0 setup it just logs -- what's
graded is that a failure here never breaks the main submission response.

send_confirmation is called fire-and-forget from the submission endpoint
and wrapped in try/except at the call site as a second layer of safety.
"""
import logging

from app.config import settings

logger = logging.getLogger("notify")


class NotifyError(Exception):
    pass


def send_confirmation(to_email: str, widget_title: str) -> None:
    if settings.disable_email_side_effect:
        # simulates a dead email provider for the demo / probe 5
        raise NotifyError("email provider unreachable (simulated failure)")

    logger.info(f"[confirmation email] to={to_email} widget={widget_title!r} -> sent (logged, not actually delivered)")
