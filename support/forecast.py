"""按"决策时点可知"的工单历史做渠道需求预测。

工单字段约定:
- channel: 原始渠道名, 可经 channel_map 归并
- created_hour: 工单创建时刻(绝对小时, 可跨天, 如 25.5 表示次日 1:30)
- known_at_hour: 该工单记录对排班可见的时刻; 缺省等于 created_hour。
  事后补录的工单 known_at_hour 晚于 created_hour, 决策时点之前的预测不得使用,
  否则历史回测会在补录之后悄悄变成"用未来信息做出的预测"。
"""

import math


def known_tickets(tickets: list[dict], as_of_hour: float) -> list[dict]:
    """只保留在 as_of_hour 之前(含)已知的工单, 防止事后补录泄漏未来信息。"""
    return [t for t in tickets if float(t.get("known_at_hour", t["created_hour"])) <= as_of_hour]


def hourly_demand(tickets: list[dict], channel_map: dict[str, str]) -> dict[tuple[str, int], int]:
    demand: dict[tuple[str, int], int] = {}
    for ticket in tickets:
        channel = channel_map.get(ticket["channel"], ticket["channel"])
        hour = int(ticket["created_hour"]) % 24
        key = (channel, hour)
        demand[key] = demand.get(key, 0) + 1
    return demand


def realized_demand(tickets: list[dict], channel_map: dict[str, str] | None = None) -> dict[tuple[str, int], int]:
    """按绝对小时统计实际来量(不折叠到 0-23), 与 forecast_demand 的键对齐。"""
    channel_map = channel_map or {}
    demand: dict[tuple[str, int], int] = {}
    for ticket in tickets:
        channel = channel_map.get(ticket["channel"], ticket["channel"])
        key = (channel, int(ticket["created_hour"]))
        demand[key] = demand.get(key, 0) + 1
    return demand


def _base_rates(history: list[dict], channel_map: dict[str, str]) -> tuple[dict[tuple[str, int], float], int]:
    """已知历史中每个 (渠道, 一天中的小时) 的平均日来量。"""
    if not history:
        return {}, 0
    counts: dict[tuple[str, int], int] = {}
    max_hour = 0.0
    for ticket in history:
        created = float(ticket["created_hour"])
        channel = channel_map.get(ticket["channel"], ticket["channel"])
        key = (channel, int(created) % 24)
        counts[key] = counts.get(key, 0) + 1
        max_hour = max(max_hour, created)
    days = max(1, int(max_hour // 24) + 1)
    return {key: value / days for key, value in counts.items()}, days


def forecast_demand(
    tickets: list[dict],
    as_of_hour: float,
    start_hour: int,
    horizon_hours: int,
    channel_map: dict[str, str] | None = None,
    holiday_uplift: dict[str, float] | None = None,
    migration: dict[tuple[str, str], float] | None = None,
    volume_factor: float | dict[str, float] = 1.0,
) -> dict:
    """用 as_of_hour 之前已知工单的小时均值, 外推 [start_hour, start_hour + horizon_hours)。

    - holiday_uplift: {渠道: 倍数}, 节假日上浮
    - migration: {(源渠道, 目标渠道): 份额}, 渠道迁移(先迁移再乘浮动)
    - volume_factor: 标量或 {渠道: 倍数}, 来量波动

    返回带 decision_hour 的快照; 快照一旦生成, 之后补录的工单不会改变它。
    """
    channel_map = channel_map or {}
    holiday_uplift = holiday_uplift or {}
    migration = migration or {}
    history = known_tickets(tickets, as_of_hour)
    base, days = _base_rates(history, channel_map)
    channels = sorted({channel for channel, _ in base})
    for src, dst in migration:
        channels.extend([src, dst])
    channels = sorted(set(channels))

    # 渠道迁移: 份额按源渠道基础量搬到目标渠道
    moved: dict[tuple[str, int], float] = {}
    for (src, dst), share in migration.items():
        for hod in range(24):
            amount = base.get((src, hod), 0.0) * share
            moved[(src, hod)] = moved.get((src, hod), 0.0) - amount
            moved[(dst, hod)] = moved.get((dst, hod), 0.0) + amount

    def factor(channel: str) -> float:
        if isinstance(volume_factor, dict):
            return float(volume_factor.get(channel, 1.0))
        return float(volume_factor)

    expected: dict[tuple[str, int], float] = {}
    for hour in range(start_hour, start_hour + horizon_hours):
        hod = hour % 24
        for channel in channels:
            rate = base.get((channel, hod), 0.0) + moved.get((channel, hod), 0.0)
            rate *= holiday_uplift.get(channel, 1.0) * factor(channel)
            expected[(channel, hour)] = rate
    return {
        "decision_hour": as_of_hour,
        "start_hour": start_hour,
        "horizon_hours": horizon_hours,
        "history_days": days,
        "history_tickets": len(history),
        "expected": expected,
    }


def forecast_error(forecast: dict, tickets: list[dict], channel_map: dict[str, str] | None = None) -> dict:
    """预测快照与窗口内实际工单的对照: 各渠道偏差与逐小时平均绝对误差。"""
    start = forecast["start_hour"]
    end = start + forecast["horizon_hours"]
    window = [t for t in tickets if start <= float(t["created_hour"]) < end]
    realized = realized_demand(window, channel_map)
    expected = forecast["expected"]
    channels = sorted({c for c, _ in expected} | {c for c, _ in realized})
    by_channel: dict[str, dict] = {}
    for channel in channels:
        exp_total = 0.0
        real_total = 0
        abs_sum = 0.0
        for hour in range(start, end):
            e = expected.get((channel, hour), 0.0)
            r = realized.get((channel, hour), 0)
            exp_total += e
            real_total += r
            abs_sum += abs(e - r)
        by_channel[channel] = {
            "expected_total": exp_total,
            "realized_total": real_total,
            "bias": exp_total - real_total,
            "hourly_mae": abs_sum / forecast["horizon_hours"],
        }
    return {
        "decision_hour": forecast["decision_hour"],
        "window": [start, end],
        "by_channel": by_channel,
        "expected_total": sum(v["expected_total"] for v in by_channel.values()),
        "realized_total": sum(v["realized_total"] for v in by_channel.values()),
    }
