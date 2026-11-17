"""离散事件重演: 按工单到达、处理时长、语言技能与班次边界推演服务。

核心不变量: 同一员工同一时刻至多服务一张工单——多技能员工不会被两个渠道
各算一次。班次终点不含在覆盖中; 员工若交班时仍在处理工单, 会把当前工单处理完
再走(计为加班), 但不会接新工单。

语言匹配约定: 员工未声明 languages(或为空)视为通配; 工单未声明 language 时
任何在岗员工都可服务。
"""

import heapq


def _language_ok(agent_langs: list[str] | None, ticket_lang: str | None) -> bool:
    return not agent_langs or not ticket_lang or ticket_lang in agent_langs


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, -(-pct * len(ordered) // 100) - 1))
    return ordered[int(rank)]


def simulate(
    tickets: list[dict],
    bookings: list[dict],
    agents: dict[str, dict],
    patience: dict[str, float | None] | None = None,
    horizon_end: float | None = None,
) -> dict:
    """重演一段业务日。

    tickets: [{channel, language?, created_hour, handle_hours, id?}]
    bookings: [{agent_id, channel, start_hour, end_hour}]
    agents: {agent_id: {"languages": [...], ...}}
    patience: {渠道: 可等待小时数, None 表示不放弃}(如语音很短、异步很长)
    horizon_end: 重演截止时刻; 届时仍在队列的工单记为 backlog(积压)
    """
    patience = patience or {}
    all_tickets: list[dict] = []
    records: list[dict] = []
    for index, raw in enumerate(tickets):
        all_tickets.append(
            {
                "id": raw.get("id", f"t{index}"),
                "channel": raw["channel"],
                "language": raw.get("language"),
                "created_hour": float(raw["created_hour"]),
                "handle_hours": float(raw["handle_hours"]),
                "status": "arriving",
            }
        )
    if horizon_end is None:
        ends = [float(b["end_hour"]) for b in bookings] + [t["created_hour"] for t in all_tickets]
        horizon_end = max(ends) if ends else 0.0
    horizon_end = float(horizon_end)

    events: list[tuple] = []
    seq = 0

    def push(time: float, kind: str, payload) -> None:
        nonlocal seq
        heapq.heappush(events, (float(time), seq, kind, payload))
        seq += 1

    for ticket in all_tickets:
        push(ticket["created_hour"], "arrival", ticket)
    for booking in bookings:
        push(booking["start_hour"], "shift_start", booking)
        push(booking["end_hour"], "shift_end", booking)

    agent_bookings: dict[str, list[dict]] = {}
    for booking in bookings:
        agent_bookings.setdefault(booking["agent_id"], []).append(booking)
    for own in agent_bookings.values():
        own.sort(key=lambda b: (b["start_hour"], b["end_hour"]))

    waiting: list[dict] = []
    idle: dict[str, dict] = {}
    busy: dict[str, dict] = {}
    service_intervals: list[dict] = []
    busy_hours = {aid: 0.0 for aid in agents}
    overtime_hours = {aid: 0.0 for aid in agents}
    boundary_hours = sorted({float(b["end_hour"]) for b in bookings} | {horizon_end})
    backlog_snapshots: list[dict] = []
    max_backlog: dict[str, int] = {}

    def langs_of(agent_id: str) -> list[str]:
        return list(agents[agent_id].get("languages") or [])

    def covering_booking(agent_id: str, now: float) -> dict | None:
        for booking in agent_bookings.get(agent_id, []):
            if booking["start_hour"] <= now < booking["end_hour"]:
                return booking
        return None

    def note_backlog() -> None:
        for ticket in waiting:
            count = sum(1 for t in waiting if t["channel"] == ticket["channel"])
            if count > max_backlog.get(ticket["channel"], 0):
                max_backlog[ticket["channel"]] = count

    def start_service(agent_id: str, booking: dict, ticket: dict, now: float) -> None:
        if agent_id in busy:
            raise RuntimeError(f"员工 {agent_id} 被重复派单")
        end = now + ticket["handle_hours"]
        ticket["status"] = "serving"
        busy[agent_id] = {"ticket": ticket, "booking": booking, "start": now, "end": end}
        push(end, "service_end", agent_id)

    def try_assign(agent_id: str, booking: dict, now: float) -> bool:
        for ticket in list(waiting):
            if ticket["channel"] != booking["channel"]:
                continue
            if not _language_ok(langs_of(agent_id), ticket["language"]):
                continue
            waiting.remove(ticket)
            start_service(agent_id, booking, ticket, now)
            return True
        return False

    def snapshot(hour: float) -> None:
        by_channel: dict[str, int] = {}
        for ticket in waiting:
            by_channel[ticket["channel"]] = by_channel.get(ticket["channel"], 0) + 1
        backlog_snapshots.append(
            {"hour": hour, "by_channel": by_channel, "total": sum(by_channel.values())}
        )

    while events:
        now, _, kind, payload = heapq.heappop(events)
        while boundary_hours and boundary_hours[0] < now:
            snapshot(boundary_hours.pop(0))
        if kind == "arrival":
            ticket = payload
            ticket["status"] = "waiting"
            assigned = False
            for agent_id in sorted(idle):
                booking = idle[agent_id]
                if booking["channel"] != ticket["channel"]:
                    continue
                if not _language_ok(langs_of(agent_id), ticket["language"]):
                    continue
                del idle[agent_id]
                start_service(agent_id, booking, ticket, now)
                assigned = True
                break
            if not assigned:
                waiting.append(ticket)
                limit = patience.get(ticket["channel"])
                if limit is not None:
                    push(now + float(limit), "abandon", ticket)
        elif kind == "shift_start":
            agent_id = payload["agent_id"]
            if agent_id in busy:
                continue  # 上一班次的工单尚未处理完, 交班后在 service_end 再衔接
            if not try_assign(agent_id, payload, now):
                idle[agent_id] = payload
        elif kind == "shift_end":
            agent_id = payload["agent_id"]
            if idle.get(agent_id) is payload:
                del idle[agent_id]
            # 若正忙: 处理完当前工单再走, 超出班次终点的部分计加班
        elif kind == "service_end":
            agent_id = payload
            done = busy.pop(agent_id)
            ticket = done["ticket"]
            booking = done["booking"]
            ticket["status"] = "served"
            busy_hours[agent_id] += now - done["start"]
            shift_end = float(booking["end_hour"])
            handed_over = any(
                other is not booking
                and float(other["start_hour"]) <= shift_end < float(other["end_hour"])
                for other in agent_bookings.get(agent_id, [])
            )
            if not handed_over:
                overtime_hours[agent_id] += max(0.0, now - shift_end)
            service_intervals.append(
                {"agent_id": agent_id, "start": done["start"], "end": now, "ticket_id": ticket["id"]}
            )
            records.append(
                {
                    "id": ticket["id"],
                    "channel": ticket["channel"],
                    "language": ticket["language"],
                    "created_hour": ticket["created_hour"],
                    "status": "served",
                    "wait_hours": done["start"] - ticket["created_hour"],
                    "service_start": done["start"],
                    "service_end": now,
                    "agent_id": agent_id,
                }
            )
            nxt = covering_booking(agent_id, now)
            if nxt is not None:
                if not try_assign(agent_id, nxt, now):
                    idle[agent_id] = nxt
        elif kind == "abandon":
            ticket = payload
            if ticket["status"] != "waiting":
                continue
            ticket["status"] = "abandoned"
            waiting.remove(ticket)
            records.append(
                {
                    "id": ticket["id"],
                    "channel": ticket["channel"],
                    "language": ticket["language"],
                    "created_hour": ticket["created_hour"],
                    "status": "abandoned",
                    "wait_hours": now - ticket["created_hour"],
                    "service_start": None,
                    "service_end": None,
                    "agent_id": None,
                }
            )
        note_backlog()

    for hour in boundary_hours:
        if hour <= horizon_end:
            snapshot(hour)

    for ticket in waiting:
        ticket["status"] = "backlog"
        records.append(
            {
                "id": ticket["id"],
                "channel": ticket["channel"],
                "language": ticket["language"],
                "created_hour": ticket["created_hour"],
                "status": "backlog",
                "wait_hours": horizon_end - ticket["created_hour"],
                "service_start": None,
                "service_end": None,
                "agent_id": None,
            }
        )

    summary: dict[str, dict] = {}
    channels = sorted({t["channel"] for t in all_tickets})
    for channel in channels:
        own = [r for r in records if r["channel"] == channel]
        waits = [r["wait_hours"] for r in own if r["status"] == "served"]
        summary[channel] = {
            "arrived": len(own),
            "served": sum(1 for r in own if r["status"] == "served"),
            "abandoned": sum(1 for r in own if r["status"] == "abandoned"),
            "backlog": sum(1 for r in own if r["status"] == "backlog"),
            "wait_p50_hours": _percentile(waits, 50),
            "wait_p90_hours": _percentile(waits, 90),
            "wait_max_hours": max(waits) if waits else 0.0,
        }

    return {
        "tickets": records,
        "service_intervals": service_intervals,
        "backlog_snapshots": backlog_snapshots,
        "max_backlog": max_backlog,
        "agents": {
            aid: {
                "busy_hours": busy_hours[aid],
                "overtime_hours": overtime_hours[aid],
                "shift_hours": sum(
                    float(b["end_hour"]) - float(b["start_hour"]) for b in agent_bookings.get(aid, [])
                ),
            }
            for aid in agents
        },
        "horizon_end": horizon_end,
        "summary": summary,
    }


def assert_single_server(result: dict) -> None:
    """校验同一员工的服务区间互不重叠(多技能人力不被两个渠道重复消耗)。"""
    by_agent: dict[str, list[dict]] = {}
    for interval in result["service_intervals"]:
        by_agent.setdefault(interval["agent_id"], []).append(interval)
    for agent_id, intervals in by_agent.items():
        intervals.sort(key=lambda i: i["start"])
        for prev, nxt in zip(intervals, intervals[1:]):
            if nxt["start"] < prev["end"] - 1e-9:
                raise AssertionError(f"员工 {agent_id} 的服务区间重叠: {prev} 与 {nxt}")
