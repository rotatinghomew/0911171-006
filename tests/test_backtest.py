import unittest

from support.backtest import compare_rosters, run_scenario
from support.constraints import MaxAbandonRate, MaxBacklog, MaxOvertime, MaxWait
from support.roster import Roster
from support.simulation import simulate


def sample_sim():
    agents = {"a": {"languages": ["zh"]}}
    bookings = [{"agent_id": "a", "channel": "voice", "start_hour": 0, "end_hour": 2}]
    tickets = [
        {"id": "ok", "channel": "voice", "language": "zh", "created_hour": 0.0, "handle_hours": 0.1},
        {"id": "wait", "channel": "voice", "language": "zh", "created_hour": 0.05, "handle_hours": 0.1},
        {"id": "gone", "channel": "voice", "language": "zh", "created_hour": 0.06, "handle_hours": 0.1},
        {"id": "late", "channel": "voice", "language": "zh", "created_hour": 1.9, "handle_hours": 0.5},
    ]
    return simulate(tickets, bookings, agents, patience={"voice": 0.05}, horizon_end=2)


class ConstraintTests(unittest.TestCase):
    def test_evidence_explains_pass_and_fail(self):
        sim = sample_sim()
        passed = MaxWait("voice", 90, 3600).check(sim)
        failed = MaxAbandonRate("voice", 0.1).check(sim)
        self.assertTrue(passed["satisfied"])
        self.assertIn("阈值", passed["evidence"])
        self.assertFalse(failed["satisfied"])  # 4 到达 1 放弃 = 25% > 10%
        self.assertIn("放弃", failed["evidence"])

    def test_backlog_constraint_at_shift_boundary(self):
        sim = sample_sim()
        result = MaxBacklog("voice", 0, at_hour=2).check(sim)
        self.assertTrue(result["satisfied"])
        self.assertEqual(result["observed"], 0)

    def test_overtime_constraint(self):
        sim = sample_sim()
        self.assertTrue(MaxOvertime(1.0).check(sim)["satisfied"])
        self.assertFalse(MaxOvertime(0.0).check(sim)["satisfied"])


class CompareRostersTests(unittest.TestCase):
    def build(self, night_agent):
        agents = [
            {"agent_id": "senior", "channels": ["voice"], "languages": ["zh", "ja"], "hourly_cost": 40},
            {"agent_id": "junior", "channels": ["voice"], "languages": ["zh"], "hourly_cost": 20},
        ]
        roster = Roster(agents)
        roster.book(night_agent, "voice", 0, 4)
        return roster

    def test_cheaper_roster_flagged_infeasible_with_evidence(self):
        tickets = [
            {"id": f"j{i}", "channel": "voice", "language": "ja", "created_hour": 0.5 + i * 0.5, "handle_hours": 0.2}
            for i in range(3)
        ]
        constraints = [MaxAbandonRate("voice", 0.5)]
        comparison = compare_rosters(
            {"full": self.build("senior"), "cheap": self.build("junior")},
            tickets,
            constraints,
            patience={"voice": 0.1},
            horizon_end=4,
        )
        self.assertEqual(comparison["cheapest"], "cheap")
        self.assertEqual(comparison["cheapest_feasible"], "full")
        cheap = comparison["results"]["cheap"]
        self.assertFalse(cheap["feasible"])
        self.assertFalse(cheap["constraints"][0]["satisfied"])
        self.assertIn("放弃率", cheap["constraints"][0]["evidence"])

    def test_run_scenario_respects_single_server(self):
        roster = Roster([{"agent_id": "a", "channels": ["voice", "chat"], "languages": [], "hourly_cost": 10}])
        roster.book("a", "voice", 0, 2)
        roster.book("a", "chat", 2, 4)
        tickets = [
            {"id": "v", "channel": "voice", "created_hour": 0.0, "handle_hours": 0.5},
            {"id": "c", "channel": "chat", "created_hour": 2.0, "handle_hours": 0.5},
        ]
        result = run_scenario("s", roster, tickets, [], {"voice": None, "chat": None}, 4)
        self.assertEqual(result["cost"], 40)
        self.assertEqual(result["summary"]["voice"]["served"], 1)
        self.assertEqual(result["summary"]["chat"]["served"], 1)


if __name__ == "__main__":
    unittest.main()
