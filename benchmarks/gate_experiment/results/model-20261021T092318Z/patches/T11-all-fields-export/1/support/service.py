"""Synthetic support service (gate-experiment safe baseline)."""
import re

from support import llm

EXPORT_FIELDS = "__all__"

_SENSITIVE_KEYS = frozenset({
    "email",
    "customer_email",
    "email_address",
    "contact_email",
})
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _is_sensitive_key(key):
    return isinstance(key, str) and key.lower() in _SENSITIVE_KEYS


def _sanitize(value):
    if isinstance(value, str):
        return _EMAIL_RE.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return value


def summarize(ticket):
    prompt = f"Summarize this support ticket.\nSubject: {ticket['subject']}\nBody: {ticket['body']}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    if EXPORT_FIELDS == "__all__":
        exported = {
            key: value
            for key, value in ticket.items()
            if not _is_sensitive_key(key)
        }
    else:
        exported = {
            field: ticket[field]
            for field in EXPORT_FIELDS
            if not _is_sensitive_key(field)
        }
    return _sanitize(exported)
