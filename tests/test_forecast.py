import unittest

from support.forecast import forecast_demand, forecast_error, known_tickets, realized_demand


class KnownTicketsTests(unittest.TestCase):
    def test_backfilled_ticket_invisible_to_earlier_decision(self):
        tickets = [
            {"channel": "voice", "created_hour": 10.0},
            {"channel": "voice", "created_hour": 11.0, "known_at_hour": 100.0},
        ]
        self.assertEqual(len(known_tickets(tickets, 50)), 1)
        self.assertEqual(len(known_tickets(tickets, 100)), 2)

    def test_backfill_does_not_change_past_forecast_snapshot(self):
        """历史回测不能在事后补录工单后变成用未来信息做出的预测。"""
        tickets = [{"channel": "voice", "created_hour": float(h)} for h in range(24)]
        snapshot = forecast_demand(tickets, as_of_hour=24, start_hour=24, horizon_hours=48)
        expected_before = dict(snapshot["expected"])
        # 决策之后补录了一批"创建于过去"的工单
        tickets.extend({"channel": "voice", "created_hour": float(h), "known_at_hour": 48.0} for h in range(24))
        self.assertEqual(snapshot["expected"], expected_before)
        # 同一决策时点重新预测, 结果也不受补录影响
        again = forecast_demand(tickets, as_of_hour=24, start_hour=24, horizon_hours=48)
        self.assertEqual(again["expected"], expected_before)
        # 而决策时点之后, 补录工单可见
        later = forecast_demand(tickets, as_of_hour=48, start_hour=24, horizon_hours=48)
        self.assertGreater(later["expected"][("voice", 30)], expected_before[("voice", 30)])


class ForecastTests(unittest.TestCase):
    def setUp(self):
        # 一天历史, 每小时 1 单语音
        self.history = [{"channel": "voice", "created_hour": float(h)} for h in range(24)]

    def test_holiday_uplift_and_volume_factor(self):
        forecast = forecast_demand(
            self.history, as_of_hour=24, start_hour=24, horizon_hours=24,
            holiday_uplift={"voice": 1.5}, volume_factor={"voice": 2.0},
        )
        self.assertAlmostEqual(forecast["expected"][("voice", 30)], 3.0)

    def test_channel_migration_shifts_volume(self):
        forecast = forecast_demand(
            self.history, as_of_hour=24, start_hour=24, horizon_hours=24,
            migration={("voice", "chat"): 0.2},
        )
        self.assertAlmostEqual(forecast["expected"][("voice", 30)], 0.8)
        self.assertAlmostEqual(forecast["expected"][("chat", 30)], 0.2)

    def test_channel_map_applied_before_aggregation(self):
        history = [{"channel": "phone", "created_hour": 3.0}]
        forecast = forecast_demand(history, as_of_hour=24, start_hour=24, horizon_hours=24, channel_map={"phone": "voice"})
        self.assertIn(("voice", 27), forecast["expected"])

    def test_forecast_error_compares_window(self):
        forecast = forecast_demand(self.history, as_of_hour=24, start_hour=24, horizon_hours=24)
        realized = [{"channel": "voice", "created_hour": 24.5}, {"channel": "voice", "created_hour": 24.6}]
        error = forecast_error(forecast, realized)
        self.assertEqual(error["by_channel"]["voice"]["realized_total"], 2)
        self.assertAlmostEqual(error["by_channel"]["voice"]["expected_total"], 24.0)
        self.assertEqual(realized_demand(realized)[("voice", 24)], 2)


if __name__ == "__main__":
    unittest.main()
