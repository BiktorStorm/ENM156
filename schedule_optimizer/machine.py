class machine:
    def __init__(self, kilowattage: int, name: str) -> None:

        self.kilowattage: int = 0
        self.name: str = name

        self.setKW(kilowattage)

    def __str__ (self):
        return self.name

    def getKW(self):
        return self.kilowattage

    def setKW(self, kilowattage: int):
        if kilowattage <= 0:
            raise ValueError("Kilowattage must be positive")
        self.kilowattage = kilowattage

    def getName(self):
        return self.name

    def setName(self, name: str):
        self.name = name

    def toDict(self) -> dict:
        return {"name": self.name, "kW": self.kilowattage}
