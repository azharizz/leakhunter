import json
import unittest
from unittest.mock import patch

from billing import service

PAYMENT = {"payment_id": "p-1", "amount": 25, "currency": "EUR", "card_number": "4111", "cvv": "123",
           "api_token": "tok"}


class ServiceTest(unittest.TestCase):
    def test_charge_returns_receipt(self):
        receipt = service.charge(PAYMENT)
        self.assertEqual((receipt["payment_id"], receipt["status"], receipt["amount"]), ("p-1", "charged", 25))

    def test_invalid_amount_is_rejected(self):
        self.assertEqual(service.charge(dict(PAYMENT, amount=0))["status"], "rejected")

    def test_notify_posts_payment_status(self):
        with patch("urllib.request.urlopen") as urlopen:
            self.assertTrue(service.notify(PAYMENT)["notified"])
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual((body["payment_id"], body["status"]), ("p-1", "paid"))
