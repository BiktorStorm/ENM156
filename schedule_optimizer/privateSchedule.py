import process

class schedule:
    def __init__ (self):
        self.maxCap: int = None
        self.processTimeline: list[dict] = []

    def addProcess (self, process: process.process, time: int):
        self.processTimeline.append({
            "startIndex": time,
            "process": process,
        })
        
    def removeProcess (self, process: process.process):
        self.processTimeline = [p for p in self.processTimeline if p["process"] != process]
        
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
    