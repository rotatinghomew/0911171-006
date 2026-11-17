from .capacity import capacity
from .forecast import hourly_demand


def compare(tickets: list[dict], channel_map: dict[str, str], shifts: list[dict]) -> dict:
    demand = hourly_demand(tickets, channel_map)
    staffed = capacity(shifts)
    periods = sorted(set(demand) | set(staffed))
    return {
        "periods": len(periods),
        "undercovered": [key for key in periods if demand.get(key, 0) > staffed.get(key, 0)],
        "uncovered_tickets": sum(max(0, demand.get(key, 0) - staffed.get(key, 0)) for key in periods),
    }
