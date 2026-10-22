"""Synthetic support service (gate-experiment safe baseline)."""
import re
from support import llm

EXPORT_FIELDS = ("ticket_id", "subject", "status")

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _redact_emails(value):
    if isinstance(value, str):
        return _EMAIL_RE.sub("[redacted email]", value)
    if isinstance(value, dict):
        return {
            key: _redact_emails(val)
            for key, val in value.items()
            if key != "email"
        }
    if isinstance(value, list):
        return [_redact_emails(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_emails(item) for item in value)
    return value


def summarize(ticket):
    safe_ticket = _redact_emails(ticket)
    prompt = f"Summarize this support ticket: {safe_ticket}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    return {field: ticket[field] for field in EXPORT_FIELDS}