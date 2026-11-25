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

    def getPrivateProfile(self) -> list[float]:
        """Power (kW) used by the company's own processes for every quarter of the day."""
        return [self.private.getTotalPowerAtIndex(i)
                for i in range(timeUtils.QUARTERS_PER_DAY)]

    def getProcessBlocks(self) -> list[dict]:
        """Every scheduled process as a time block, sorted by start time.
        dependsOn: ids of the processes it waits for.
        minStart/maxStart: the start window its dependencies allow.
        allowedStarts: starts in that window that are inside working hours.
        outsideHours: True if it currently runs outside the working hours."""
        timeline = self.private.processTimeline
        idOf = {id(entry["process"]): i for i, entry in enumerate(timeline)}
        blocks = []
        for blockId, entry in enumerate(timeline):
            proc = entry["process"]
            start = entry["startIndex"]
            end = start + proc.getDurationQuarter()
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
                "allowedStarts": self.private.workingHours.allowedStarts(
                    proc.getDurationQuarter(), self.private.earliestStart(proc),
                    self.private.latestStart(proc)),
                "outsideHours": not self.private.workingHours.allows(
                    start, proc.getDurationQuarter()),
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

    def moveProcess(self, processId: int, newStartIndex: int) -> dict:
        """Moves a process to a new start quarter. Returns its new block.
        Refuses moves that would break a dependency order."""
        self.private.moveProcess(self.getProcessById(processId), newStartIndex)
        return self.getBlock(processId)

    def setDependencies(self, processId: int, dependencyIds: list[int]) -> list[int]:
        """Process processId may only start once all dependencyIds are done.
        Returns the ids of processes that had to be pushed later."""
        proc = self.getProcessById(processId)
        deps = [self.getProcessById(d) for d in dependencyIds]
        moved = self.private.setDependencies(proc, deps)
        return [i for i, entry in enumerate(self.private.processTimeline)
                if any(entry["process"] is m for m in moved)]

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
