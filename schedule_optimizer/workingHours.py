import timeUtils

# The hours a factory can run, in quarters (see timeUtils). #
#
# A process must lie completely inside [start, end) and may not overlap the
# lunch break [lunchStart, lunchEnd). By default the whole day is open and
# there is no lunch.

class workingHours:
    def __init__(self, start: int = 0, end: int = timeUtils.QUARTERS_PER_DAY,
                 lunchStart: int | None = None, lunchEnd: int | None = None):
        self.start = 0
        self.end = timeUtils.QUARTERS_PER_DAY
        self.lunchStart: int | None = None
        self.lunchEnd: int | None = None
        self.set(start, end, lunchStart, lunchEnd)

    def set(self, start: int, end: int,
            lunchStart: int | None = None, lunchEnd: int | None = None):
        if not 0 <= start < end <= timeUtils.QUARTERS_PER_DAY:
            raise ValueError("Working hours must start before they end, "
                             "within 00:00–24:00")
        if (lunchStart is None) != (lunchEnd is None):
            raise ValueError("Give both a lunch start and a lunch end, or neither")
        if lunchStart is not None:
            if not start <= lunchStart < lunchEnd <= end:
                raise ValueError("Lunch must start before it ends and lie "
                                 "within the working hours")
        self.start, self.end = start, end
        self.lunchStart, self.lunchEnd = lunchStart, lunchEnd

    def hasLunch(self) -> bool:
        return self.lunchStart is not None

    def isWorking(self, quarter: int) -> bool:
        if not self.start <= quarter < self.end:
            return False
        return not (self.hasLunch() and self.lunchStart <= quarter < self.lunchEnd)

    def allows(self, startIndex: int, duration: int) -> bool:
        """True if a process can run from startIndex for duration quarters."""
        return duration > 0 and all(
            self.isWorking(q) for q in range(startIndex, startIndex + duration))

    def allowedStarts(self, duration: int, first: int = 0,
                      last: int = timeUtils.QUARTERS_PER_DAY) -> list[int]:
        """Every allowed start in [first, last]."""
        return [s for s in range(max(first, 0), last + 1)
                if self.allows(s, duration)]

    def nextAllowedStart(self, fromIndex: int, duration: int) -> int | None:
        starts = self.allowedStarts(duration, fromIndex)
        return starts[0] if starts else None

    def describe(self) -> str:
        text = f"{timeUtils.indexToTime(self.start)}–{timeUtils.indexToTime(self.end)}"
        if self.hasLunch():
            text += (f", lunch {timeUtils.indexToTime(self.lunchStart)}–"
                     f"{timeUtils.indexToTime(self.lunchEnd)}")
        return text

    def toDict(self) -> dict:
        def time(index):
            return None if index is None else timeUtils.indexToTime(index)
        return {"start": time(self.start), "end": time(self.end),
                "lunchStart": time(self.lunchStart), "lunchEnd": time(self.lunchEnd),
                "startIndex": self.start, "endIndex": self.end,
                "lunchStartIndex": self.lunchStart, "lunchEndIndex": self.lunchEnd}
