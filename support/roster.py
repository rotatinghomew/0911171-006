from copy import deepcopy

from .backtest import compare


class Roster:
    def __init__(self, agents: list[dict]) -> None:
        self.agents = {agent["agent_id"]: deepcopy(agent) for agent in agents}
        if len(self.agents) != len(agents):
            raise ValueError("员工编号重复")
        self.bookings: list[dict] = []

    def book(self, agent_id: str, channel: str, start_hour: int, end_hour: int) -> None:
        agent = self.agents[agent_id]
        if channel not in agent["channels"]:
            raise ValueError("员工不具备该渠道技能")
        if start_hour >= end_hour:
            raise ValueError("班次终点必须晚于起点")
        for booking in self.bookings:
            if booking["agent_id"] == agent_id and max(start_hour, booking["start_hour"]) < min(end_hour, booking["end_hour"]):
                raise ValueError("同一员工的班次不能重叠")
        self.bookings.append({"agent_id": agent_id, "channel": channel, "start_hour": start_hour, "end_hour": end_hour})

    def coverage(self) -> list[dict]:
        return [{**booking, "agents": 1} for booking in deepcopy(self.bookings)]

    def cost(self) -> float:
        return sum(
            (booking["end_hour"] - booking["start_hour"]) * float(self.agents[booking["agent_id"]]["hourly_cost"])
            for booking in self.bookings
        )

    def assess(self, tickets: list[dict], channel_map: dict[str, str]) -> dict:
        return {"coverage": compare(tickets, channel_map, self.coverage()), "cost": self.cost()}
