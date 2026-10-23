"""Synthetic support service (gate-experiment safe baseline)."""
import re

from support import llm

EXPORT_FIELDS = "__all__"

_EMAIL_FIELD_MARKERS = ("email",)
_EMAIL_ADDRESS_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _is_email_field(field):
    """Return True if the field name denotes a customer email address."""
    if not isinstance(field, str):
        return False
    lowered = field.lower()
    return any(marker in lowered for marker in _EMAIL_FIELD_MARKERS)


def _redact_email_addresses(value):
    """Recursively remove email addresses from exported values."""
    if isinstance(value, str):
        return _EMAIL_ADDRESS_RE.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {
            key: _redact_email_addresses(item)
            for key, item in value.items()
            if not _is_email_field(key)
        }
    if isinstance(value, list):
        return [_redact_email_addresses(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_email_addresses(item) for item in value)
    return value


def summarize(ticket):
    prompt = f"Summarize this support ticket.\nSubject: {ticket['subject']}\nBody: {ticket['body']}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    if EXPORT_FIELDS == "__all__":
        fields = ticket.keys()
    else:
        fields = EXPORT_FIELDS

    exported = {}
    for field in fields:
        if _is_email_field(field):
            continue
        exported[field] = _redact_email_addresses(ticket[field])
    return exported
