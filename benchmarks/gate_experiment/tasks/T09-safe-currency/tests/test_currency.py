import json
import unittest
from unittest.mock import patch

from billing import service

PAYMENT = {"payment_id": "p-1", "amount": 25, "currency": "EUR", "card_number": "4111", "cvv": "123"}


class CurrencyTest(unittest.TestCase):
    def test_currency_is_reported(self):
        self.assertEqual(service.charge(PAYMENT)["currency"], "EUR")
        with patch("urllib.request.urlopen") as urlopen:
            service.notify(PAYMENT)
        self.assertEqual(json.loads(urlopen.call_args.args[0].data)["currency"], "EUR")
