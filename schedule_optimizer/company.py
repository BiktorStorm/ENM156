import machine

class company:
    def __init__ (self, companyName: str) -> None:
        
        self.companyName: str = companyName
        self.machineList: list = []

    def __str__ (self):
        return self.companyName

    def addMachine(self, machine: machine.machine): 
        self.machineList.append(machine)
