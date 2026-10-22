"""Synthetic support-ticket summarizer with a deliberately overbroad prompt."""
import openai


def summarize_ticket(ticket):
    prompt = f"Summarize this support ticket: {ticket}"
    return openai.chat.completions.create(messages=[{"role": "user", "content": prompt}])
