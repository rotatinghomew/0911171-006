"""本地重放: 节假日多语种业务日的排班情景回测。

情节: 第 14 天是节假日。排班决策在业务日(08:00 至次日 08:00)开始前做出,
预测只能使用当时已知的工单历史(前 14 天), 并显式保留渠道迁移(voice→chat)、
节假日上浮与来量波动参数。随后用同一批实际工单重演两份班表, 比较等待、放弃、
跨班积压与人员成本; 再用"预测水平"与"实际水平"两个需求情景对照,
看需求误差怎样传到服务结果。
"""

import random

from .backtest import compare_rosters, run_scenario
from .constraints import MaxAbandonRate, MaxBacklog, MaxOvertime, MaxWait
from .forecast import forecast_demand, forecast_error
from .roster import Roster

CHANNELS = ("voice", "chat", "email")
LANGS = (("zh", 0.70), ("en", 0.20), ("ja", 0.10))
HANDLE_HOURS = {"voice": 6 / 60, "chat": 8 / 60, "email": 12 / 60}
PATIENCE_HOURS = {"voice": 4 / 60, "chat": 0.5, "email": None}  # 语音不能久等, 异步可以等
HOLIDAY_UPLIFT = {"voice": 1.30, "chat": 1.15, "email": 1.0}
MIGRATION = {("voice", "chat"): 0.05}  # 5% 的语音需求迁到在线消息
REALIZED_VOLUME = {"voice": 1.20, "chat": 1.12, "email": 1.10}  # 决策时未知的来量波动

DAY = 14
DAY_START = DAY * 24 + 8  # 业务日 08:00 开始
HORIZON_HOURS = 24
HORIZON_END = DAY_START + HORIZON_HOURS  # 次日 08:00
MIDNIGHT = DAY_START + 16  # 晚班与夜班(00:00-08:00)的交接点


def profile(channel: str, hod: int) -> float:
    """各渠道一天中每小时的基础到达率(单/小时)。"""
    if channel == "voice":
        if 9 <= hod < 18:
            return 7.0
        if 18 <= hod < 23:
            return 7.0
        if hod >= 23 or hod < 6:
            return 2.0
        return 4.0
    if channel == "chat":
        return 4.5 if 8 <= hod < 23 else 0.5
    return 3.0 if 6 <= hod < 22 else 1.0


def _poisson(rng: random.Random, lam: float) -> int:
    limit = pow(2.718281828459045, -lam)
    count, product = 0, 1.0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1


def _pick_language(rng: random.Random) -> str:
    roll = rng.random()
    acc = 0.0
    for lang, share in LANGS:
        acc += share
        if roll < acc:
            return lang
    return LANGS[-1][0]


def gen_window(
    rng: random.Random,
    start_hour: float,
    hours: int,
    holiday: bool = False,
    migration: dict | None = None,
    volume: dict[str, float] | None = None,
) -> list[dict]:
    """生成 [start_hour, start_hour + hours) 的工单; known_at_hour 略晚于创建时刻。"""
    volume = volume or {}
    migration = migration or {}
    tickets = []
    for channel in CHANNELS:
        for offset in range(hours):
            hod = int(start_hour + offset) % 24
            lam = profile(channel, hod)
            for (src, dst), share in migration.items():
                if channel == src:
                    lam *= 1 - share
                if channel == dst:
                    lam += profile(src, hod) * share
            if holiday:
                lam *= HOLIDAY_UPLIFT.get(channel, 1.0)
            lam *= volume.get(channel, 1.0)
            for _ in range(_poisson(rng, lam)):
                created = start_hour + offset + rng.random()
                tickets.append(
                    {
                        "channel": channel,
                        "language": _pick_language(rng),
                        "created_hour": created,
                        "handle_hours": HANDLE_HOURS[channel] * (0.6 + 0.8 * rng.random()),
                        "known_at_hour": created + 0.05 + 0.1 * rng.random(),
                    }
                )
    tickets.sort(key=lambda t: t["created_hour"])
    for index, ticket in enumerate(tickets):
        ticket["id"] = f"w{int(start_hour)}-{index}"
    return tickets


def gen_history(days: int) -> list[dict]:
    rng = random.Random(20261001)
    history = []
    for day in range(days):
        history.extend(gen_window(rng, day * 24, 24))
    return history


def build_rosters() -> dict[str, Roster]:
    """baseline: 晚班双语音坐席且夜班覆盖日语; cheap: 砍晚班第二坐席与夜班日语技能。"""
    day, swing, night = DAY_START, DAY_START + 8, DAY_START + 16
    agents = [
        {"agent_id": "a1", "channels": ["voice", "chat"], "languages": ["zh", "en", "ja"], "hourly_cost": 30},
        {"agent_id": "a2", "channels": ["voice"], "languages": ["zh", "en", "ja"], "hourly_cost": 38},
        {"agent_id": "a3", "channels": ["chat"], "languages": ["zh", "en"], "hourly_cost": 22},
        {"agent_id": "a4", "channels": ["email", "chat"], "languages": ["zh", "en"], "hourly_cost": 20},
        {"agent_id": "a5", "channels": ["voice", "chat"], "languages": ["zh", "en"], "hourly_cost": 30},
        {"agent_id": "a6", "channels": ["voice"], "languages": ["zh", "en", "ja"], "hourly_cost": 36},
        {"agent_id": "a7", "channels": ["voice"], "languages": ["zh", "en", "ja"], "hourly_cost": 42},
        {"agent_id": "a7b", "channels": ["voice"], "languages": ["zh", "en"], "hourly_cost": 40},
        {"agent_id": "a8", "channels": ["chat", "email"], "languages": ["zh", "en", "ja"], "hourly_cost": 26},
        {"agent_id": "a9", "channels": ["chat"], "languages": ["zh", "en", "ja"], "hourly_cost": 28},
        {"agent_id": "a10", "channels": ["chat"], "languages": ["zh", "en", "ja"], "hourly_cost": 24},
        {"agent_id": "a10b", "channels": ["chat"], "languages": ["zh", "en"], "hourly_cost": 24},
        {"agent_id": "a11", "channels": ["voice"], "languages": ["zh", "en"], "hourly_cost": 30},
    ]

    def shifts(roster: Roster, evening_ja: bool, night_agent: str, evening_email: bool) -> Roster:
        roster.book("a1", "voice", day, day + 8)
        roster.book("a2", "voice", day, day + 8)
        roster.book("a11", "voice", day, day + 8)
        roster.book("a3", "chat", day, day + 8)
        roster.book("a9", "chat", day, day + 8)
        roster.book("a4", "email", day, day + 8)
        if evening_email:
            roster.book("a4", "email", day + 8, day + 14)  # 晚班兼顾异步积压到 22:00
        roster.book("a5", "voice", swing, swing + 8)
        roster.book("a10", "chat", swing, swing + 8)
        roster.book("a10b", "chat", swing, swing + 8)
        if evening_ja:
            roster.book("a6", "voice", swing, swing + 8)
        roster.book(night_agent, "voice", night, night + 8)  # 夜班 00:00-08:00 跨午夜
        if evening_email:
            roster.book("a8", "chat", night, night + 4)
            roster.book("a8", "email", night + 4, night + 8)  # 后半夜清理异步积压
        else:
            roster.book("a8", "chat", night, night + 8)  # 省钱做法: 夜间不清理异步积压
        return roster

    baseline = shifts(Roster([dict(a) for a in agents]), evening_ja=True, night_agent="a7", evening_email=True)
    cheap = shifts(Roster([dict(a) for a in agents]), evening_ja=False, night_agent="a7b", evening_email=False)
    return {"baseline": baseline, "cheap": cheap}


def build_constraints() -> list:
    return [
        MaxWait("voice", 90, 120),
        MaxAbandonRate("voice", 0.05),
        MaxWait("chat", 90, 600),
        MaxAbandonRate("chat", 0.05),
        MaxBacklog("voice", 2, at_hour=MIDNIGHT),
        MaxBacklog("email", 10),
        MaxOvertime(1.0),
    ]


def show_result(result: dict) -> None:
    print(f"  班表 {result['name']}: 成本 {result['cost']:.0f}, 约束 {'全部满足' if result['feasible'] else '未全部满足'}")
    for channel in CHANNELS:
        s = result["summary"].get(channel)
        if not s:
            continue
        print(
            f"    {channel:5s} 到达 {s['arrived']:3d} 服务 {s['served']:3d} 放弃 {s['abandoned']:2d} "
            f"积压 {s['backlog']:2d} 等待p90 {s['wait_p90_hours'] * 3600:5.0f}s 最长 {s['wait_max_hours'] * 3600:5.0f}s"
        )
    for snap in result["sim"]["backlog_snapshots"]:
        print(f"    小时 {snap['hour']:.0f} 跨班积压: {snap['by_channel'] or '{}'}")
    for check in result["constraints"]:
        mark = "✓" if check["satisfied"] else "✗"
        print(f"    {mark} {check['name']} —— {check['evidence']}")


def main() -> None:
    history = gen_history(DAY)
    forecast = forecast_demand(
        history,
        as_of_hour=DAY_START,
        start_hour=DAY_START,
        horizon_hours=HORIZON_HOURS,
        holiday_uplift=HOLIDAY_UPLIFT,
        migration=MIGRATION,
        volume_factor=1.0,
    )
    realized = gen_window(
        random.Random(20261117), DAY_START, HORIZON_HOURS,
        holiday=True, migration=MIGRATION, volume=REALIZED_VOLUME,
    )
    planned = gen_window(
        random.Random(20261117), DAY_START, HORIZON_HOURS,
        holiday=True, migration=MIGRATION, volume={},
    )

    print("== 预测(只用决策时点已知的工单) ==")
    print(
        f"  决策时点: 小时 {forecast['decision_hour']:.0f}, 使用历史 {forecast['history_days']} 天 "
        f"共 {forecast['history_tickets']} 单; 节假日上浮 {HOLIDAY_UPLIFT}, 渠道迁移 {MIGRATION}"
    )
    error = forecast_error(forecast, realized)
    for channel, stats in error["by_channel"].items():
        print(
            f"    {channel:5s} 预测 {stats['expected_total']:6.1f} 实际 {stats['realized_total']:3d} "
            f"偏差 {stats['bias']:+6.1f} 逐小时MAE {stats['hourly_mae']:.2f}"
        )
    print(f"    合计  预测 {error['expected_total']:.1f} 实际 {error['realized_total']}")

    constraints = build_constraints()
    rosters = build_rosters()

    print("\n== 情景一: 需求与预测一致时, baseline 班表的服务结果 ==")
    show_result(run_scenario("baseline", rosters["baseline"], planned, constraints, PATIENCE_HOURS, HORIZON_END))

    print("\n== 情景二: 同一实际业务日, 对比两份班表 ==")
    comparison = compare_rosters(
        {"baseline": rosters["baseline"], "cheap": rosters["cheap"]},
        realized,
        constraints,
        PATIENCE_HOURS,
        HORIZON_END,
    )
    for name in ("baseline", "cheap"):
        show_result(comparison["results"][name])
    print(
        f"\n  结论: 最便宜班表 {comparison['cheapest']}, 可行班表 {comparison['feasible'] or '无'}, "
        f"最便宜可行班表 {comparison['cheapest_feasible'] or '无'}"
    )
    print("  更便宜的班表未必可用: 上面的 ✗ 与积压快照给出了不可用的具体依据,")
    print("  需求波动(预测偏差)则解释了 baseline 在两个情景间服务结果的差距。")


if __name__ == "__main__":
    main()
