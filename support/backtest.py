from .capacity import capacity
from .forecast import hourly_demand
from .simulation import assert_single_server, simulate


def compare(tickets: list[dict], channel_map: dict[str, str], shifts: list[dict]) -> dict:
    demand = hourly_demand(tickets, channel_map)
    staffed = capacity(shifts)
    periods = sorted(set(demand) | set(staffed))
    return {
        "periods": len(periods),
        "undercovered": [key for key in periods if demand.get(key, 0) > staffed.get(key, 0)],
        "uncovered_tickets": sum(max(0, demand.get(key, 0) - staffed.get(key, 0)) for key in periods),
    }


def run_scenario(
    name: str,
    roster,
    tickets: list[dict],
    constraints: list | None = None,
    patience: dict[str, float | None] | None = None,
    horizon_end: float | None = None,
) -> dict:
    """在同一需求情景(一批工单)下重演一份排班, 并逐条核对服务约束。"""
    sim = simulate(tickets, roster.coverage(), roster.agents, patience=patience, horizon_end=horizon_end)
    assert_single_server(sim)
    checks = [constraint.check(sim) for constraint in (constraints or [])]
    return {
        "name": name,
        "cost": roster.cost(),
        "sim": sim,
        "constraints": checks,
        "feasible": all(check["satisfied"] for check in checks),
        "summary": sim["summary"],
    }


def compare_rosters(
    rosters: dict,
    tickets: list[dict],
    constraints: list | None = None,
    patience: dict[str, float | None] | None = None,
    horizon_end: float | None = None,
) -> dict:
    """同一需求情景下对比多份排班: 等待、放弃、跨班积压与人员成本。"""
    results = {
        name: run_scenario(name, roster, tickets, constraints, patience, horizon_end)
        for name, roster in rosters.items()
    }
    cheapest = min(results.values(), key=lambda r: r["cost"])["name"] if results else None
    feasible = [name for name, result in results.items() if result["feasible"]]
    return {
        "results": results,
        "cheapest": cheapest,
        "feasible": feasible,
        "cheapest_feasible": min(feasible, key=lambda n: results[n]["cost"]) if feasible else None,
    }
