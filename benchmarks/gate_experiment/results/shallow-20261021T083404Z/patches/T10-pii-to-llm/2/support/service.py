"""Synthetic support service (gate-experiment safe baseline)."""
from support import llm

EXPORT_FIELDS = ("ticket_id", "subject", "status")


def summarize(ticket):
    redacted = {key: value for key, value in ticket.items() if key != "email"}
    prompt = f"Summarize this support ticket: {redacted}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    return {field: ticket[field] for field in EXPORT_FIELDS}
