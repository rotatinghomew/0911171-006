import unittest

from support.simulation import assert_single_server, simulate


def make_ticket(tid, channel, created, handle, language=None):
    return {"id": tid, "channel": channel, "language": language, "created_hour": created, "handle_hours": handle}


class SingleServerTests(unittest.TestCase):
    def test_one_agent_never_double_consumed(self):
        """多技能员工同一份人力不能被两个渠道同时消耗。"""
        agents = {"a": {"languages": ["zh", "en"]}}
        bookings = [
            {"agent_id": "a", "channel": "voice", "start_hour": 0, "end_hour": 4},
            {"agent_id": "a", "channel": "chat", "start_hour": 4, "end_hour": 8},
        ]
        tickets = [make_ticket(f"t{i}", "voice", 0.1 * i, 0.5, "zh") for i in range(6)]
        tickets += [make_ticket(f"c{i}", "chat", 4.0 + 0.1 * i, 0.5, "en") for i in range(4)]
        result = simulate(tickets, bookings, agents, horizon_end=8)
        assert_single_server(result)
        busy = result["agents"]["a"]["busy_hours"]
        self.assertLessEqual(busy, result["agents"]["a"]["shift_hours"] + 1e-9)

    def test_simulation_rejects_double_assignment_internally(self):
        agents = {"a": {}}
        bookings = [{"agent_id": "a", "channel": "chat", "start_hour": 0, "end_hour": 2}]
        tickets = [make_ticket("x", "chat", 0.0, 1.0), make_ticket("y", "chat", 0.0, 1.0)]
        result = simulate(tickets, bookings, agents, horizon_end=4)
        served = [t for t in result["tickets"] if t["status"] == "served"]
        self.assertEqual(len(served), 2)
        intervals = sorted((t["service_start"], t["service_end"]) for t in served)
        self.assertGreaterEqual(intervals[1][0], intervals[0][1])


class LanguageSkillTests(unittest.TestCase):
    def test_ticket_waits_for_matching_language(self):
        agents = {"en": {"languages": ["en"]}, "ja": {"languages": ["ja"]}}
        bookings = [
            {"agent_id": "en", "channel": "voice", "start_hour": 0, "end_hour": 4},
            {"agent_id": "ja", "channel": "voice", "start_hour": 2, "end_hour": 4},
        ]
        tickets = [make_ticket("j1", "voice", 0.5, 0.5, "ja")]
        result = simulate(tickets, bookings, agents, horizon_end=4)
        ticket = result["tickets"][0]
        self.assertEqual(ticket["status"], "served")
        self.assertEqual(ticket["agent_id"], "ja")
        self.assertAlmostEqual(ticket["wait_hours"], 1.5)

    def test_unmatched_language_never_served(self):
        agents = {"en": {"languages": ["en"]}}
        bookings = [{"agent_id": "en", "channel": "voice", "start_hour": 0, "end_hour": 4}]
        tickets = [make_ticket("j1", "voice", 0.5, 0.5, "ja")]
        result = simulate(tickets, bookings, agents, patience={"voice": None}, horizon_end=4)
        self.assertEqual(result["tickets"][0]["status"], "backlog")


class PatienceTests(unittest.TestCase):
    def test_voice_abandons_after_patience(self):
        tickets = [make_ticket("v1", "voice", 0.0, 0.5)]
        result = simulate(tickets, [], {}, patience={"voice": 0.25}, horizon_end=2)
        ticket = result["tickets"][0]
        self.assertEqual(ticket["status"], "abandoned")
        self.assertAlmostEqual(ticket["wait_hours"], 0.25)

    def test_async_ticket_waits_as_backlog(self):
        tickets = [make_ticket("e1", "email", 0.0, 0.5)]
        result = simulate(tickets, [], {}, patience={"email": None}, horizon_end=2)
        self.assertEqual(result["tickets"][0]["status"], "backlog")
        self.assertEqual(result["summary"]["email"]["abandoned"], 0)


class ShiftBoundaryTests(unittest.TestCase):
    def test_no_service_outside_shift(self):
        agents = {"a": {}}
        bookings = [{"agent_id": "a", "channel": "chat", "start_hour": 1, "end_hour": 2}]
        tickets = [make_ticket("early", "chat", 0.0, 0.25), make_ticket("late", "chat", 2.5, 0.25)]
        result = simulate(tickets, bookings, agents, patience={"chat": None}, horizon_end=4)
        early = next(t for t in result["tickets"] if t["id"] == "early")
        late = next(t for t in result["tickets"] if t["id"] == "late")
        self.assertGreaterEqual(early["service_start"], 1.0)
        self.assertEqual(late["status"], "backlog")

    def test_finish_current_ticket_counts_overtime(self):
        agents = {"a": {}}
        bookings = [{"agent_id": "a", "channel": "voice", "start_hour": 0, "end_hour": 1}]
        tickets = [make_ticket("v", "voice", 0.9, 0.5)]
        result = simulate(tickets, bookings, agents, horizon_end=2)
        self.assertEqual(result["tickets"][0]["status"], "served")
        self.assertAlmostEqual(result["agents"]["a"]["overtime_hours"], 0.4)

    def test_back_to_back_shift_handover_is_not_overtime(self):
        agents = {"a": {}}
        bookings = [
            {"agent_id": "a", "channel": "email", "start_hour": 0, "end_hour": 1},
            {"agent_id": "a", "channel": "email", "start_hour": 1, "end_hour": 2},
        ]
        tickets = [make_ticket("e", "email", 0.9, 0.5)]
        result = simulate(tickets, bookings, agents, patience={"email": None}, horizon_end=2)
        self.assertEqual(result["tickets"][0]["status"], "served")
        self.assertAlmostEqual(result["agents"]["a"]["overtime_hours"], 0.0)

    def test_cross_shift_backlog_snapshot(self):
        agents = {"a": {}}
        bookings = [{"agent_id": "a", "channel": "chat", "start_hour": 0, "end_hour": 1}]
        tickets = [make_ticket("c1", "chat", 0.5, 2.0), make_ticket("c2", "chat", 0.6, 0.5)]
        result = simulate(tickets, bookings, agents, patience={"chat": None}, horizon_end=2)
        snapshots = {s["hour"]: s for s in result["backlog_snapshots"]}
        self.assertEqual(snapshots[1]["by_channel"].get("chat"), 1)  # 交班时 c2 仍在排队


if __name__ == "__main__":
    unittest.main()
