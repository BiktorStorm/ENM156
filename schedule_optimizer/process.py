import machine

class process:
    def __init__ (self, machine: machine.machine, duration: int):
        self.duration = duration
        self.machine = machine

    def getDurationQuarter (self):
        return self.duration 

    def getDuration (self):
        return self.duration * 15

    def setDuration (self, time: int):
        self.duration = time