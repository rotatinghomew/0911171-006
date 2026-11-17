def hourly_demand(tickets: list[dict], channel_map: dict[str, str]) -> dict[tuple[str, int], int]:
    demand: dict[tuple[str, int], int] = {}
    for ticket in tickets:
        channel = channel_map.get(ticket["channel"], ticket["channel"])
        hour = int(ticket["created_hour"]) % 24
        key = (channel, hour)
        demand[key] = demand.get(key, 0) + 1
    return demand
