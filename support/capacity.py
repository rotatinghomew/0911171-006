def capacity(shifts: list[dict]) -> dict[tuple[str, int], int]:
    result: dict[tuple[str, int], int] = {}
    for shift in shifts:
        for hour in range(shift["start_hour"], shift["end_hour"]):
            key = (shift["channel"], hour % 24)
            result[key] = result.get(key, 0) + int(shift["agents"])
    return result
