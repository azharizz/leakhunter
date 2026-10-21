import unittest

from support import service


class PriorityTest(unittest.TestCase):
    def test_priority_is_exported(self):
        ticket = {"ticket_id": "s-1", "subject": "Billing", "status": "open", "priority": "high", "body": "x"}
        self.assertEqual(service.export_ticket(ticket)["priority"], "high")
