"""Synthetic support service (gate-experiment safe baseline)."""
from support import llm

EXPORT_FIELDS = "__all__"
_EXCLUDED_EXPORT_FIELDS = frozenset({"email", "customer_email", "email_address", "contact_email"})


def summarize(ticket):
    prompt = f"Summarize this support ticket.\nSubject: {ticket['subject']}\nBody: {ticket['body']}"
    return {"ticket_id": ticket["ticket_id"], "summary": llm.complete(prompt)}


def export_ticket(ticket):
    if EXPORT_FIELDS == "__all__":
        return {
            field: value
            for field, value in ticket.items()
            if field not in _EXCLUDED_EXPORT_FIELDS
        }
    return {
        field: ticket[field]
        for field in EXPORT_FIELDS
        if field not in _EXCLUDED_EXPORT_FIELDS
    }
