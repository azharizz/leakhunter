"""Reference repair that projects the synthetic ticket fields sent to the model."""
import openai


def summarize_ticket(ticket):
    prompt = f"Summarize this ticket: {ticket['ticket_id']} — {ticket['subject']}"
    return openai.chat.completions.create(messages=[{"role": "user", "content": prompt}])
