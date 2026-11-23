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
        
    def getTotalPowerAtIndex (self, index: int):
        sumKW = 0
        for process in self.processTimeline:
            if process["startIndex"] <= index \
            and index <= (process["startIndex"] + process["process"].getDuration()):
                sumKW += process["process"].machine.kilowattage
        return sumKW