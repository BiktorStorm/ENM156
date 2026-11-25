import machine

class process:
    def __init__ (self, machine: machine.machine, duration: int):
        self.duration = duration
        self.machine = machine
        # Processes that must be finished before this one may start.
        # An empty list means the process is independent.
        self.dependencies: list["process"] = []

    def getDurationQuarter (self):
        return self.duration

    def getDuration (self):
        return self.duration * 15

    def setDuration (self, time: int):
        self.duration = time

    def getKWh(self):
        return (self.duration / 60) * self.machine.getKW()

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
