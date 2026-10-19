"""Synthetic vendor SDK boundary: local outbox instead of a real recipient.

Runtime capture_calls observes track's actual arguments before this adapter runs.
No request is sent and no customer data is persisted, even outside the harness.
"""
import json

OUTBOX: list[dict] = []


def track(event: str, payload: dict) -> dict:
    envelope = json.loads(json.dumps({"event": event, "properties": payload}))
    OUTBOX.append(envelope)
    return {"accepted": True}
