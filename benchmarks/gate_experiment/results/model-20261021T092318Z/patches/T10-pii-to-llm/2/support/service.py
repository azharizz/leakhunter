'''Synthetic support service (gate-experiment safe baseline).'''
import re
from support import llm

EXPORT_FIELDS = ('ticket_id', 'subject', 'status')

_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def _redact_emails(value):
    if isinstance(value, str):
        return _EMAIL_RE.sub('[REDACTED_EMAIL]', value)
    return value


def summarize(ticket):
    safe_ticket = {
        key: _redact_emails(value)
        for key, value in ticket.items()
        if key != 'email'
    }
    prompt = f'Summarize this support ticket: {safe_ticket}'
    return {'ticket_id': ticket['ticket_id'], 'summary': llm.complete(prompt)}


def export_ticket(ticket):
    return {field: ticket[field] for field in EXPORT_FIELDS}
