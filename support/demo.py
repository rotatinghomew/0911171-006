from .roster import Roster


def main() -> None:
    tickets = [{"channel": "chat", "created_hour": 22}, {"channel": "chat", "created_hour": 22}]
    roster = Roster([{"agent_id": "a1", "channels": ["chat"], "hourly_cost": 20}])
    roster.book("a1", "chat", 20, 24)
    print(roster.assess(tickets, {"live-chat": "chat"}))


if __name__ == "__main__":
    main()
