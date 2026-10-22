import unittest
from unittest.mock import patch

from support import service

TICKET = {"ticket_id": "s-1", "subject": "Billing", "body": "Please update my plan", "status": "open",
          "priority": "high", "email": "c@example.invalid", "phone": "+1555", "internal_notes": "vip"}


class ServiceTest(unittest.TestCase):
    def test_summarize_uses_the_model_summary(self):
        with patch("support.llm.complete", return_value="A billing question") as complete:
            result = service.summarize(TICKET)
        self.assertEqual(result, {"ticket_id": "s-1", "summary": "A billing question"})
        self.assertIn("Billing", complete.call_args.args[0])

    def test_export_ticket(self):
        exported = service.export_ticket(TICKET)
        self.assertEqual((exported["ticket_id"], exported["subject"], exported["status"]), ("s-1", "Billing", "open"))
