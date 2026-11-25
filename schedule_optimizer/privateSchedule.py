import process
import timeUtils
import workingHours

class schedule:
    def __init__ (self):
        self.maxCap: int = None
        self.processTimeline: list[dict] = []
        # Shared with the company (see InterfaceGUI), whole day by default
        self.workingHours = workingHours.workingHours()

    def addProcess (self, process: process.process, time: int):
        self.checkWorkingHours(process, time)
        self.processTimeline.append({
            "startIndex": time,
            "process": process,
        })

    def removeProcess (self, process: process.process):
        self.processTimeline = [p for p in self.processTimeline if p["process"] != process]
        # Nothing can wait for a process that is no longer scheduled
        for entry in self.processTimeline:
            entry["process"].removeDependency(process)

    def getTotalPowerAtIndex (self, index: int):
        sumKW: float = 0
        for process in self.processTimeline:
            if process["startIndex"] <= index \
            and index < (process["startIndex"] + process["process"].getDurationQuarter()):
                sumKW += process["process"].machine.kilowattage
        return sumKW

    def getTotalPowerTimeline (self):
        totalPowerTimeline: list[float] = []
        for index in range(0, 96): #all quarters in a day
            totalPowerTimeline.append(self.getTotalPowerAtIndex(index))
        return totalPowerTimeline

    # -------------------------- Dependencies ------------------------- #
    # If B depends on A, B may not start before A has finished:
    #     start(B) >= start(A) + duration(A)

    def getEntry(self, proc: process.process) -> dict:
        for entry in self.processTimeline:
            if entry["process"] is proc:
                return entry
        raise KeyError("The process is not in the schedule")

    def getStart(self, proc: process.process) -> int:
        return self.getEntry(proc)["startIndex"]

    def getEnd(self, proc: process.process) -> int:
        return self.getStart(proc) + proc.getDurationQuarter()

    def isScheduled(self, proc: process.process) -> bool:
        return any(entry["process"] is proc for entry in self.processTimeline)

    def getDependents(self, proc: process.process) -> list[process.process]:
        """Scheduled processes that wait directly for proc."""
        return [entry["process"] for entry in self.processTimeline
                if any(d is proc for d in entry["process"].dependencies)]

    def earliestStart(self, proc: process.process) -> int:
        """Earliest start that keeps proc after all its dependencies."""
        ends = [self.getEnd(d) for d in proc.dependencies if self.isScheduled(d)]
        return max(ends, default=0)

    def latestStart(self, proc: process.process) -> int:
        """Latest start that still finishes before its dependents start."""
        starts = [self.getStart(d) for d in self.getDependents(proc)]
        latest = min(starts, default=timeUtils.QUARTERS_PER_DAY)
        return latest - proc.getDurationQuarter()

    def moveProcess(self, proc: process.process, newStart: int):
        """Moves proc, refusing moves that break the day or a dependency."""
        lastStart = timeUtils.QUARTERS_PER_DAY - proc.getDurationQuarter()
        if not 0 <= newStart <= lastStart:
            raise ValueError(
                f"Start must be between 00:00 and "
                f"{timeUtils.indexToTime(lastStart)} for this process")
        self.checkWorkingHours(proc, newStart)
        earliest, latest = self.earliestStart(proc), self.latestStart(proc)
        if newStart < earliest:
            raise ValueError(
                f"{proc.machine.name} must wait for its dependencies and "
                f"cannot start before {timeUtils.indexToTime(earliest)}")
        if newStart > latest:
            raise ValueError(
                f"{proc.machine.name} must finish before a dependent process "
                f"and cannot start after {timeUtils.indexToTime(latest)}")
        self.getEntry(proc)["startIndex"] = newStart

    def setDependencies(self, proc: process.process,
                        dependencies: list[process.process]) -> list[process.process]:
        """Sets what proc waits for. If proc (or anything after it) now
        starts too early it is pushed later. Returns the moved processes.
        Nothing changes if the dependencies are invalid or do not fit in the day."""
        oldDeps = list(proc.dependencies)
        oldStarts = [(entry, entry["startIndex"]) for entry in self.processTimeline]
        proc.setDependencies(dependencies)
        try:
            return self.pushLater(proc)
        except ValueError:
            proc.dependencies = oldDeps
            for entry, start in oldStarts:
                entry["startIndex"] = start
            raise

    def pushLater(self, proc: process.process) -> list[process.process]:
        """Moves proc and its dependents later until every order holds."""
        moved = []
        earliest = self.earliestStart(proc)
        if self.getStart(proc) < earliest:
            # First start after the dependencies that is inside working hours
            newStart = self.workingHours.nextAllowedStart(
                earliest, proc.getDurationQuarter())
            if newStart is None:
                raise ValueError(
                    f"{proc.machine.name} does not fit within the working hours "
                    f"({self.workingHours.describe()}) if it waits for its dependencies")
            self.getEntry(proc)["startIndex"] = newStart
            moved.append(proc)
        for dependent in self.getDependents(proc):
            moved += [p for p in self.pushLater(dependent)
                      if not any(p is m for m in moved)]
        return moved

    # ------------------------- Working hours ------------------------- #

    def checkWorkingHours(self, proc: process.process, start: int):
        duration = proc.getDurationQuarter()
        if not self.workingHours.allows(start, duration):
            raise ValueError(
                f"{proc.machine.name} {timeUtils.indexToTime(start)}–"
                f"{timeUtils.indexToTime(start + duration)} is outside the working "
                f"hours ({self.workingHours.describe()})")

    def getWorkingHourViolations(self) -> list[process.process]:
        """Processes that run outside the working hours or during lunch,
        e.g. after the hours were changed."""
        return [entry["process"] for entry in self.processTimeline
                if not self.workingHours.allows(entry["startIndex"],
                                                entry["process"].getDurationQuarter())]

    def getDependencyViolations(self) -> list[tuple[process.process, process.process]]:
        """(dependent, dependency) pairs where the order is broken."""
        return [(entry["process"], dep)
                for entry in self.processTimeline
                for dep in entry["process"].dependencies
                if self.isScheduled(dep) and entry["startIndex"] < self.getEnd(dep)]
