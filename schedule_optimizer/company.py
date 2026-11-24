import machine

class company:
    def __init__ (self, companyName: str) -> None:

        self.companyName: str = companyName
        self.machineList: list = []
        self.maxOptimFlex: int = 8 # n number of quarters a block can move in time

    def __str__ (self):
        return self.companyName

    def getName(self) -> str:
        return self.companyName

    def setName(self, companyName: str):
        self.companyName = companyName

    def addMachine(self, machine: machine.machine):
        if self.findMachine(machine.name) is not None:
            raise ValueError(f"A machine named '{machine.name}' already exists")
        self.machineList.append(machine)

    def removeMachine(self, name: str):
        self.machineList.remove(self.getMachine(name))

    def editMachine(self, name: str, newName: str | None = None,
                    newKilowattage: int | None = None) -> machine.machine:
        targetMachine = self.getMachine(name)
        if newName is not None and newName != name:
            if self.findMachine(newName) is not None:
                raise ValueError(f"A machine named '{newName}' already exists")
            targetMachine.setName(newName)
        if newKilowattage is not None:
            targetMachine.setKW(newKilowattage)
        return targetMachine

    def findMachine(self, name: str) -> machine.machine | None:
        for m in self.machineList:
            if m.name == name:
                return m
        return None

    def getMachine(self, name: str) -> machine.machine:
        found = self.findMachine(name)
        if found is None:
            raise KeyError(f"No machine named '{name}'")
        return found

    def getMachinesInfo(self) -> list[dict]:
        return [m.toDict() for m in self.machineList]
