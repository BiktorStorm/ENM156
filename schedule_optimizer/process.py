import machine
import timeUtils

class process:
    def __init__ (self, machine: machine.machine, duration: int,
                  deadline: int | None = None):
        self.duration = duration
        self.machine = machine
        # Processes that must be finished before this one may start.
        # An empty list means the process is independent.
        self.dependencies: list["process"] = []
        # Quarter by which the process has to be finished (end <= deadline,
        # 96 = 24:00). None means no deadline.
        self.deadline: int | None = None
        self.setDeadline(deadline)

    def getDurationQuarter (self):
        return self.duration

    def getDuration (self):
        return self.duration * 15

    def setDuration (self, time: int):
        self.duration = time

    def getKWh(self):
        return (self.duration / 60) * self.machine.getKW()

    # --------------------------- Deadline ---------------------------- #

    def setDeadline(self, deadline: int | None):
        if deadline is not None:
            if (not isinstance(deadline, int) or isinstance(deadline, bool)
                    or not 0 < deadline <= timeUtils.QUARTERS_PER_DAY):
                raise ValueError("The deadline must be between 00:15 and 24:00")
            if deadline < self.duration:
                raise ValueError(
                    f"A {self.getDuration()} min process cannot be finished by "
                    f"{timeUtils.indexToTime(deadline)}")
        self.deadline = deadline

    def hasDeadline(self) -> bool:
        return self.deadline is not None

    def meetsDeadline(self, start: int) -> bool:
        """True if the process is finished in time when it starts at start."""
        return self.deadline is None or start + self.duration <= self.deadline

    # -------------------------- Dependencies ------------------------- #

    def isIndependent(self) -> bool:
        return not self.dependencies

    def dependsOn(self, other: "process") -> bool:
        """True if this process has to wait for other, directly or through
        a chain of dependencies."""
        stack, seen = list(self.dependencies), set()
        while stack:
            current = stack.pop()
            if current is other:
                return True
            if id(current) not in seen:
                seen.add(id(current))
                stack.extend(current.dependencies)
        return False

    def addDependency(self, other: "process"):
        if other is self:
            raise ValueError("A process cannot depend on itself")
        if other.dependsOn(self):
            raise ValueError("That dependency would create a cycle")
        if not any(d is other for d in self.dependencies):
            self.dependencies.append(other)

    def removeDependency(self, other: "process"):
        self.dependencies = [d for d in self.dependencies if d is not other]

    def setDependencies(self, others: list["process"]):
        """Replaces all dependencies. Nothing changes if one is invalid."""
        old = self.dependencies
        self.dependencies = []
        try:
            for other in others:
                self.addDependency(other)
        except ValueError:
            self.dependencies = old
            raise
