import unittest

from support.roster import Roster


class RosterTests(unittest.TestCase):
    def test_one_person_cannot_be_counted_in_two_concurrent_channels(self):
        roster = Roster([{"agent_id": "a", "channels": ["chat", "voice"], "hourly_cost": 20}])
        roster.book("a", "chat", 8, 10)
        with self.assertRaises(ValueError):
            roster.book("a", "voice", 9, 11)
        self.assertEqual(roster.cost(), 40)

    def test_backtest_respects_booked_channel(self):
        roster = Roster([{"agent_id": "a", "channels": ["chat"], "hourly_cost": 20}])
        roster.book("a", "chat", 8, 9)
        tickets = [{"channel": "web", "created_hour": 8}, {"channel": "phone", "created_hour": 8}]
        result = roster.assess(tickets, {"web": "chat", "phone": "voice"})
        self.assertEqual(result["coverage"]["uncovered_tickets"], 1)
        with self.assertRaises(ValueError):
            roster.book("a", "voice", 10, 11)
