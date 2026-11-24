# Time is measured in quarters (15 min), matching privateSchedule and the
# forecast data: index 0 = 00:00, index 1 = 00:15, ..., index 95 = 23:45.

QUARTERS_PER_DAY = 96
MINUTES_PER_QUARTER = 15
HOURS_PER_QUARTER = MINUTES_PER_QUARTER / 60


def indexToTime(index: int) -> str:
    minutes = index * MINUTES_PER_QUARTER
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def timeToIndex(time: str) -> int:
    """'HH:MM' -> quarter index. Rounds down to the nearest quarter."""
    hours, minutes = (int(part) for part in time.split(":"))
    return (hours * 60 + minutes) // MINUTES_PER_QUARTER
