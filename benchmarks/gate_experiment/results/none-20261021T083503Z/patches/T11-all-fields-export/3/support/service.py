"""Synthetic support service (gate-experiment safe baseline)."""
from support import llm

EXPORT_FIELDS = "__all__"


def summarize(ticket):
    prompt = f"Summarize this support ticket.\nSubject: {ticket['subject']}\nBody: {ticket['body']}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    if EXPORT_FIELDS == "__all__":
        return dict(ticket)
    return {field: ticket[field] for field in EXPORT_FIELDS}
