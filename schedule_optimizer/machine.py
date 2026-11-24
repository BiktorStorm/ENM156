class machine:
    def __init__(self, kilowattage: float, name: str) -> None:
        
        self.kilowattage: float = kilowattage

        self.kilowattage: int = 0
        self.name: str = name

        self.setKW(kilowattage)

    def __str__ (self):
        return self.name

    def getKW(self):
        return self.kilowattage
