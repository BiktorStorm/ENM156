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
        self.checkStart(process, time)
        self.processTimeline.append({
            "startIndex": time,
            "process": process,
        })

    def removeProcess (self, process: process.process):
        self.processTimeline = [p for p in self.processTimeline if p["process"] != process]
        # Nothing can wait for a process that is no longer scheduled
        for entry in self.processTimeline:
            entry["process"].removeDependency(process)

    def copy(self) -> "schedule":
        """A copy with the same processes and working hours but its own start
        times: moving a process in the copy leaves this schedule unchanged.
        Used for the optimisation preview."""
        clone = schedule()
        clone.maxCap = self.maxCap
        clone.workingHours = self.workingHours
        clone.processTimeline = [dict(entry) for entry in self.processTimeline]
        return clone

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
        """Latest start that still finishes before its dependents start
        and by its deadline."""
        starts = [self.getStart(d) for d in self.getDependents(proc)]
        latestEnd = min(starts, default=timeUtils.QUARTERS_PER_DAY)
        if proc.deadline is not None:
            latestEnd = min(latestEnd, proc.deadline)
        return latestEnd - proc.getDurationQuarter()

    def moveProcess(self, proc: process.process, newStart: int):
        """Moves proc, refusing moves that break the day, the working hours,
        its deadline, a dependency or put two processes on one machine."""
        lastStart = timeUtils.QUARTERS_PER_DAY - proc.getDurationQuarter()
        if not 0 <= newStart <= lastStart:
            raise ValueError(
                f"Start must be between 00:00 and "
                f"{timeUtils.indexToTime(lastStart)} for this process")
        self.checkWorkingHours(proc, newStart)
        self.checkDeadline(proc, newStart)
        earliest, latest = self.earliestStart(proc), self.latestStart(proc)
        if newStart < earliest:
            raise ValueError(
                f"{proc.machine.name} must wait for its dependencies and "
                f"cannot start before {timeUtils.indexToTime(earliest)}")
        if newStart > latest:
            raise ValueError(
                f"{proc.machine.name} must finish before a dependent process "
                f"and cannot start after {timeUtils.indexToTime(latest)}")
        self.checkMachineFree(proc, newStart)
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
        """Moves proc and its dependents later until every order holds.
        Each process goes to the first valid start after its dependencies
        (inside the working hours, by its deadline, machine free)."""
        moved = []
        earliest = self.earliestStart(proc)
        if self.getStart(proc) < earliest:
            newStart = self.nextValidStart(proc, earliest)
            if newStart is None:
                raise ValueError(self.noStartReason(proc, earliest))
            self.getEntry(proc)["startIndex"] = newStart
            moved.append(proc)
        for dependent in self.getDependents(proc):
            moved += [p for p in self.pushLater(dependent)
                      if not any(p is m for m in moved)]
        return moved

    # -------------------------- Valid starts ------------------------- #
    # A process may start at a quarter if it
    #   - fits inside the day,
    #   - keeps to the working hours (machines that may run outside them
    #     only have to start inside them),
    #   - is finished by its deadline, if it has one,
    #   - does not overlap another process on the same machine
    #     (a machine runs one process at a time).
    # Dependencies are handled by earliestStart/latestStart.

    def startProblem(self, proc: process.process, start: int) -> str | None:
        """Why proc cannot start at start (ignoring dependencies), or None."""
        lastStart = timeUtils.QUARTERS_PER_DAY - proc.getDurationQuarter()
        if not 0 <= start <= lastStart:
            return (f"Start must be between 00:00 and "
                    f"{timeUtils.indexToTime(lastStart)} for this process")
        return (self.workingHoursProblem(proc, start)
                or self.deadlineProblem(proc, start)
                or self.machineProblem(proc, start))

    def canStartAt(self, proc: process.process, start: int) -> bool:
        return self.startProblem(proc, start) is None

    def checkStart(self, proc: process.process, start: int):
        problem = self.startProblem(proc, start)
        if problem is not None:
            raise ValueError(problem)

    def nextValidStart(self, proc: process.process, fromIndex: int) -> int | None:
        lastStart = timeUtils.QUARTERS_PER_DAY - proc.getDurationQuarter()
        for start in range(max(fromIndex, 0), lastStart + 1):
            if self.canStartAt(proc, start):
                return start
        return None

    def noStartReason(self, proc: process.process, fromIndex: int) -> str:
        """Explains why nextValidStart(proc, fromIndex) found nothing."""
        name = proc.machine.name
        firstInHours = self.workingHours.nextAllowedStart(
            fromIndex, proc.getDurationQuarter(), proc.machine.allowOutsideHours)
        if firstInHours is None:
            return (f"{name} does not fit within the working hours "
                    f"({self.workingHours.describe()}) if it waits for its dependencies")
        if not proc.meetsDeadline(firstInHours):
            return (f"{name} cannot be finished by its deadline "
                    f"{timeUtils.indexToTime(proc.deadline)} if it waits for its dependencies")
        return (f"{name} is busy with other processes for the rest of the day "
                f"and cannot fit this one after its dependencies")

    def allowedStarts(self, proc: process.process) -> list[int]:
        """Every start that is valid and keeps the dependency order."""
        lastStart = min(self.latestStart(proc),
                        timeUtils.QUARTERS_PER_DAY - proc.getDurationQuarter())
        return [s for s in range(max(self.earliestStart(proc), 0), lastStart + 1)
                if self.canStartAt(proc, s)]

    # ------------------------- Working hours ------------------------- #

    def allowsHours(self, proc: process.process, start: int) -> bool:
        return self.workingHours.allows(start, proc.getDurationQuarter(),
                                        proc.machine.allowOutsideHours)

    def runsPastHours(self, proc: process.process, start: int) -> bool:
        """True if proc runs into lunch or closed time, which its machine
        is allowed to do."""
        return (proc.machine.allowOutsideHours and self.allowsHours(proc, start)
                and not self.workingHours.allows(start, proc.getDurationQuarter()))

    def workingHoursProblem(self, proc: process.process, start: int) -> str | None:
        if self.allowsHours(proc, start):
            return None
        duration = proc.getDurationQuarter()
        if proc.machine.allowOutsideHours:
            return (f"{proc.machine.name} may run past the working hours but has to "
                    f"start within them ({self.workingHours.describe()}), "
                    f"not at {timeUtils.indexToTime(start)}")
        return (f"{proc.machine.name} {timeUtils.indexToTime(start)}–"
                f"{timeUtils.indexToTime(start + duration)} is outside the working "
                f"hours ({self.workingHours.describe()})")

    def checkWorkingHours(self, proc: process.process, start: int):
        problem = self.workingHoursProblem(proc, start)
        if problem is not None:
            raise ValueError(problem)

    def getWorkingHourViolations(self) -> list[process.process]:
        """Processes that run outside the working hours or during lunch,
        e.g. after the hours were changed."""
        return [entry["process"] for entry in self.processTimeline
                if not self.allowsHours(entry["process"], entry["startIndex"])]

    # --------------------------- Deadlines --------------------------- #

    def deadlineProblem(self, proc: process.process, start: int) -> str | None:
        if proc.meetsDeadline(start):
            return None
        return (f"{proc.machine.name} {timeUtils.indexToTime(start)}–"
                f"{timeUtils.indexToTime(start + proc.getDurationQuarter())} ends after "
                f"its deadline {timeUtils.indexToTime(proc.deadline)}")

    def checkDeadline(self, proc: process.process, start: int):
        problem = self.deadlineProblem(proc, start)
        if problem is not None:
            raise ValueError(problem)

    def getDeadlineViolations(self) -> list[process.process]:
        """Processes that end after their deadline, e.g. after the deadline
        was set."""
        return [entry["process"] for entry in self.processTimeline
                if not entry["process"].meetsDeadline(entry["startIndex"])]

    # ---------------------- Machine availability --------------------- #

    def machineConflicts(self, proc: process.process, start: int) -> list[process.process]:
        """Other scheduled processes on proc's machine that would run at the
        same time as proc if it started at start."""
        end = start + proc.getDurationQuarter()
        return [entry["process"] for entry in self.processTimeline
                if entry["process"] is not proc
                and entry["process"].machine is proc.machine
                and entry["startIndex"] < end
                and start < entry["startIndex"] + entry["process"].getDurationQuarter()]

    def machineProblem(self, proc: process.process, start: int) -> str | None:
        busy = self.machineConflicts(proc, start)
        if not busy:
            return None
        other = self.getEntry(busy[0])
        otherEnd = other["startIndex"] + busy[0].getDurationQuarter()
        return (f"{proc.machine.name} is already running a process "
                f"{timeUtils.indexToTime(other['startIndex'])}–"
                f"{timeUtils.indexToTime(otherEnd)} and can only run one at a time")

    def checkMachineFree(self, proc: process.process, start: int):
        problem = self.machineProblem(proc, start)
        if problem is not None:
            raise ValueError(problem)

    def getOverlapViolations(self) -> list[tuple[process.process, process.process]]:
        """Pairs of processes that run at the same time on the same machine."""
        pairs = []
        for i, a in enumerate(self.processTimeline):
            aEnd = a["startIndex"] + a["process"].getDurationQuarter()
            for b in self.processTimeline[i + 1:]:
                bEnd = b["startIndex"] + b["process"].getDurationQuarter()
                if (a["process"].machine is b["process"].machine
                        and a["startIndex"] < bEnd and b["startIndex"] < aEnd):
                    pairs.append((a["process"], b["process"]))
        return pairs

    def getDependencyViolations(self) -> list[tuple[process.process, process.process]]:
        """(dependent, dependency) pairs where the order is broken."""
        return [(entry["process"], dep)
                for entry in self.processTimeline
                for dep in entry["process"].dependencies
                if self.isScheduled(dep) and entry["startIndex"] < self.getEnd(dep)]
