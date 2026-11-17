import unittest

from support.backtest import compare


class SupportTests(unittest.TestCase):
    def test_backtest_finds_undercovered_period(self):
        result = compare([{"channel": "chat", "created_hour": 9}] * 3, {}, [{"channel": "chat", "start_hour": 9, "end_hour": 10, "agents": 1}])
        self.assertEqual(result["uncovered_tickets"], 2)

    def test_empty_periods(self):
        self.assertEqual(compare([], {}, []) ["periods"], 0)


if __name__ == "__main__":
    unittest.main()
