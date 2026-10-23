"""Synthetic billing service (gate-experiment safe baseline)."""
import json
import logging
from urllib import request

log = logging.getLogger("billing")
log.setLevel(logging.INFO)
WEBHOOK_URL = "https://hooks.example.invalid/payments"


def receipt(payment):
    return {"payment_id": payment["payment_id"], "amount": payment["amount"], "status": "charged"}


def charge(payment):
    log.info("charging payment %s for amount %s", payment["payment_id"], payment["amount"])
    if payment["amount"] <= 0:
        log.warning("rejected payment %s: invalid amount", payment["payment_id"])
        return {"payment_id": payment["payment_id"], "status": "rejected"}
    return receipt(payment)


def notify(payment):
    body = json.dumps({"payment_id": payment["payment_id"], "status": "paid", "amount": payment["amount"]})
    request.urlopen(request.Request(WEBHOOK_URL, data=body.encode(), method="POST"), timeout=5)
    return {"notified": True, "payment_id": payment["payment_id"]}
