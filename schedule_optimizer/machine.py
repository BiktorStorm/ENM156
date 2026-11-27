class machine:
    def __init__(self, kilowattage: float, name: str,
                 allowOutsideHours: bool = False) -> None:

        self.kilowattage: float = 0
        self.name: str = name
        # True if a process on this machine may keep running through lunch
        # and after closing. It must still start inside the working hours.
        self.allowOutsideHours: bool = bool(allowOutsideHours)

        self.setKW(kilowattage)

    def __str__ (self):
        return self.name

    def getKW(self) -> float:
        return self.kilowattage

    def setKW(self, kilowattage: float):
        if kilowattage <= 0:
            raise ValueError("Kilowattage must be positive")
        self.kilowattage = kilowattage

    def getName(self) -> str:
        return self.name

    def setName(self, name: str):
        self.name = name

    def getAllowOutsideHours(self) -> bool:
        return self.allowOutsideHours

    def setAllowOutsideHours(self, allowed: bool):
        self.allowOutsideHours = bool(allowed)

    def toDict(self) -> dict:
        return {"name": self.name, "kW": self.kilowattage,
                "allowOutsideHours": self.allowOutsideHours}
