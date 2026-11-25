class machine:
    def __init__(self, kilowattage: float, name: str) -> None:

        self.kilowattage: float = 0
        self.name: str = name

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

    def toDict(self) -> dict:
        return {"name": self.name, "kW": self.kilowattage}
