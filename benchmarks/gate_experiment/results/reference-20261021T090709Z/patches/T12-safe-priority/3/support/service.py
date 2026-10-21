"""Synthetic support service (gate-experiment safe baseline)."""
from support import llm

EXPORT_FIELDS = ("ticket_id", "subject", "status", "priority")


def summarize(ticket):
    prompt = f"Summarize this support ticket.\nSubject: {ticket['subject']}\nBody: {ticket['body']}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    return {field: ticket[field] for field in EXPORT_FIELDS}
