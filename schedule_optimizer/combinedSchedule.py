import datetime

import areaSchedule
import privateSchedule
import process
import timeUtils

# Combines the area forecast with the company's own schedule. #
class schedule:
    def __init__ (self, area: areaSchedule.schedule,
                  private: privateSchedule.schedule):
        self.area = area
        self.private = private
        # Optimisation proposal waiting to be accepted or rejected, see
        # "Optimisation preview" below
        self.preview: dict | None = None

    def getPrivateProfile(self) -> list[float]:
        """Power (kW) used by the company's own processes for every quarter of the day."""
        return [self.private.getTotalPowerAtIndex(i)
                for i in range(timeUtils.QUARTERS_PER_DAY)]

    def getProcessBlocks(self) -> list[dict]:
        """Every scheduled process as a time block, sorted by start time.
        dependsOn: ids of the processes it waits for.
        minStart/maxStart: the start window its dependencies and deadline allow.
        allowedStarts: starts in that window that are valid (working hours,
            deadline, machine free).
        outsideHours: True if it currently runs outside the working hours.
        allowOutsideHours: its machine may run past the working hours.
        pastHours: it runs into lunch or closed time, which its machine may.
        deadlineIndex/deadline: when it has to be finished, or None.
        lateForDeadline: True if it currently ends after its deadline.
        overlapsWith: ids of processes on the same machine that run at the
            same time (should always be empty)."""
        timeline = self.private.processTimeline
        idOf = {id(entry["process"]): i for i, entry in enumerate(timeline)}
        overlaps: dict[int, list[int]] = {}
        for a, b in self.private.getOverlapViolations():
            overlaps.setdefault(idOf[id(a)], []).append(idOf[id(b)])
            overlaps.setdefault(idOf[id(b)], []).append(idOf[id(a)])
        blocks = []
        for blockId, entry in enumerate(timeline):
            proc = entry["process"]
            start = entry["startIndex"]
            end = start + proc.getDurationQuarter()
            deadline = proc.deadline
            blocks.append({
                "id": blockId,
                "machine": proc.machine.name,
                "kW": proc.machine.kilowattage,
                "startIndex": start,
                "endIndex": end,
                "startTime": timeUtils.indexToTime(start),
                "endTime": timeUtils.indexToTime(end),
                "dependsOn": [idOf[id(d)] for d in proc.dependencies if id(d) in idOf],
                "minStart": self.private.earliestStart(proc),
                "maxStart": self.private.latestStart(proc),
                "allowedStarts": self.private.allowedStarts(proc),
                "outsideHours": not self.private.allowsHours(proc, start),
                "allowOutsideHours": proc.machine.allowOutsideHours,
                "pastHours": self.private.runsPastHours(proc, start),
                "deadlineIndex": deadline,
                "deadline": None if deadline is None else timeUtils.indexToTime(deadline),
                "lateForDeadline": not proc.meetsDeadline(start),
                "overlapsWith": sorted(overlaps.get(blockId, [])),
            })
        return sorted(blocks, key=lambda b: b["startIndex"])

    def getBlock(self, processId: int) -> dict:
        return next(b for b in self.getProcessBlocks() if b["id"] == processId)

    # Process ids are the positions in privateSchedule.processTimeline, the
    # same ids getProcessBlocks() hands out. They stay the same after a move
    # but can change after a remove, so fetch the blocks again afterwards.

    def getProcessById(self, processId: int) -> process.process:
        if not 0 <= processId < len(self.private.processTimeline):
            raise KeyError(f"No process with id {processId}")
        return self.private.processTimeline[processId]["process"]

    def removeProcess(self, processId: int):
        self.private.removeProcess(self.getProcessById(processId))
        self.clearPreview()

    def moveProcess(self, processId: int, newStartIndex: int) -> dict:
        """Moves a process to a new start quarter. Returns its new block.
        Refuses moves that would break a dependency order."""
        self.private.moveProcess(self.getProcessById(processId), newStartIndex)
        self.clearPreview()
        return self.getBlock(processId)

    def setDependencies(self, processId: int, dependencyIds: list[int]) -> list[int]:
        """Process processId may only start once all dependencyIds are done.
        Returns the ids of processes that had to be pushed later."""
        proc = self.getProcessById(processId)
        deps = [self.getProcessById(d) for d in dependencyIds]
        moved = self.private.setDependencies(proc, deps)
        self.clearPreview()
        return [i for i, entry in enumerate(self.private.processTimeline)
                if any(entry["process"] is m for m in moved)]

    def setDeadline(self, processId: int, deadline: int | None) -> dict:
        """Process processId has to be finished by quarter deadline (None
        for no deadline). Returns its block: lateForDeadline is True if it
        currently ends too late and has to be moved earlier."""
        self.getProcessById(processId).setDeadline(deadline)
        self.clearPreview()
        return self.getBlock(processId)

    def getViolations(self) -> dict:
        """Ids of the processes that break a scheduling rule right now."""
        idOf = {id(entry["process"]): i
                for i, entry in enumerate(self.private.processTimeline)}
        return {
            "outsideHours": [idOf[id(p)] for p in self.private.getWorkingHourViolations()],
            "lateForDeadline": [idOf[id(p)] for p in self.private.getDeadlineViolations()],
            "overlaps": [(idOf[id(a)], idOf[id(b)])
                         for a, b in self.private.getOverlapViolations()],
            "dependencies": [(idOf[id(a)], idOf[id(b)])
                             for a, b in self.private.getDependencyViolations()],
        }

    # ---------------------- Optimisation preview --------------------- #
    # The optimiser proposes new starts on a copy of the private schedule
    # (optimize.propose_schedule). The copy is kept here, and the real
    # schedule stays as it is, until the proposal is accepted (the processes
    # move to the proposed starts) or rejected (nothing moves).
    #
    # A proposal belongs to the exact schedule it was made from. It is
    # dropped when a process is added, removed or moved, or when a rule the
    # optimiser used changes, so it can never be applied to another schedule.

    def setPreview(self, proposed: privateSchedule.schedule,
                   date: str | datetime.date, horizon: str | None = None):
        own = self.private.processTimeline
        if len(proposed.processTimeline) != len(own) or any(
                a["process"] is not b["process"]
                for a, b in zip(own, proposed.processTimeline)):
            raise ValueError("The proposal does not match the current schedule")
        self.preview = {"schedule": proposed, "date": str(date),
                        "horizon": horizon, "base": self.startSnapshot()}

    def clearPreview(self):
        self.preview = None

    def startSnapshot(self) -> list[tuple]:
        return [(entry["process"], entry["startIndex"])
                for entry in self.private.processTimeline]

    def isPreviewCurrent(self) -> bool:
        """True if there is a proposal and the schedule has not changed since."""
        if self.preview is None:
            return False
        base, now = self.preview["base"], self.startSnapshot()
        return len(base) == len(now) and all(
            p is q and s == t for (p, s), (q, t) in zip(base, now))

    def getPreview(self, date: str | datetime.date | None = None,
                   horizon: str | None = None) -> dict | None:
        """The current proposal, or None. With a date, only a proposal made
        for that date and horizon is returned.
        blocks: the processes that would move, as process blocks at their
            proposed position, with fromStartIndex/fromStartTime/fromEndTime
            (where they are now) and shift (quarters, + is later).
        before/after: day summaries of the real and the proposed schedule.
        peakReductionKW: before peak - after peak (negative = higher peak)."""
        if not self.isPreviewCurrent():
            self.preview = None
            return None
        if date is not None and (str(date), horizon) != (
                self.preview["date"], self.preview["horizon"]):
            return None

        proposed = self.preview["schedule"]
        proposed.maxCap = self.private.maxCap
        proposedView = schedule(self.area, proposed)
        current = {b["id"]: b for b in self.getProcessBlocks()}
        moved = []
        for block in proposedView.getProcessBlocks():
            now = current[block["id"]]
            if block["startIndex"] != now["startIndex"]:
                moved.append({**block,
                              "fromStartIndex": now["startIndex"],
                              "fromStartTime": now["startTime"],
                              "fromEndTime": now["endTime"],
                              "shift": block["startIndex"] - now["startIndex"]})

        date, horizon = self.preview["date"], self.preview["horizon"]
        before = self.getDaySummary(date, horizon)
        after = proposedView.getDaySummary(date, horizon)
        return {"date": date, "horizon": horizon,
                "blocks": moved, "movedIds": [b["id"] for b in moved],
                "before": before, "after": after,
                "peakReductionKW": before["peakTotalKW"] - after["peakTotalKW"]}

    def acceptPreview(self) -> dict:
        """Moves the processes to the proposed starts and drops the proposal.
        Returns the proposal as it was before it was applied."""
        if self.preview is None:
            raise ValueError("There is no optimisation proposal to accept. "
                             "Press Optimize day first.")
        result = self.getPreview()
        if result is None:
            raise ValueError("The schedule changed after the optimisation was "
                             "proposed. Press Optimize day again.")

        timeline = self.private.processTimeline
        oldStarts = [entry["startIndex"] for entry in timeline]
        for entry, proposedEntry in zip(timeline, self.preview["schedule"].processTimeline):
            entry["startIndex"] = proposedEntry["startIndex"]

        # Safety net: a moved process must never end up late or share its
        # machine with another process
        moved = [entry["process"] for entry, old in zip(timeline, oldStarts)
                 if entry["startIndex"] != old]
        late = [p for p in moved if not p.meetsDeadline(self.private.getStart(p))]
        clash = [pair for pair in self.private.getOverlapViolations()
                 if any(p is m for p in pair for m in moved)]
        if late or clash:
            for entry, old in zip(timeline, oldStarts):
                entry["startIndex"] = old
            self.preview = None
            raise RuntimeError("The proposal breaks a deadline or puts two processes "
                               "on one machine at once, it was not applied")

        self.preview = None
        return result

    def getCombinedProfile(self, date: str | datetime.date,
                           horizon: str | None = None) -> list[dict]:
        """Area forecast and company load side by side, one row per quarter."""
        areaValues = self.area.getDay(date, horizon)
        maxCap = self.private.maxCap

        rows = []
        for i, areaKW in enumerate(areaValues):
            privateKW = self.private.getTotalPowerAtIndex(i)
            totalKW = areaKW + privateKW
            rows.append({
                "index": i,
                "time": timeUtils.indexToTime(i),
                "areaKW": areaKW,
                "privateKW": privateKW,
                "totalKW": totalKW,
                "overCapacity": maxCap is not None and totalKW > maxCap,
            })
        return rows

    def getCapacityViolations(self, date: str | datetime.date,
                              horizon: str | None = None) -> list[dict]:
        """Quarters where total power is above the max capacity."""
        return [row for row in self.getCombinedProfile(date, horizon)
                if row["overCapacity"]]

    def getDaySummary(self, date: str | datetime.date,
                      horizon: str | None = None) -> dict:
        profile = self.getCombinedProfile(date, horizon)
        peak = max(profile, key=lambda r: r["totalKW"])
        return {
            "date": str(date),
            "horizon": horizon,
            "processCount": len(self.private.processTimeline),
            "maxCapacityKW": self.private.maxCap,
            "peakTotalKW": peak["totalKW"],
            "peakTime": peak["time"],
            "areaEnergyKWh": sum(r["areaKW"] for r in profile) * timeUtils.HOURS_PER_QUARTER,
            "privateEnergyKWh": sum(r["privateKW"] for r in profile) * timeUtils.HOURS_PER_QUARTER,
            "violationCount": sum(1 for r in profile if r["overCapacity"]),
        }
