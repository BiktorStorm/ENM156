class machine:
    def __init__(self, kilowattage: int, name: str) -> None:
        
        self.kilowattage: int = kilowattage

        self.name: str = name

    def __str__ (self):
        return self.name    

    def getKW(self):
        return 