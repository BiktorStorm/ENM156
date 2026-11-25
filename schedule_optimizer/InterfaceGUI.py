import datetime
from pathlib import Path

import company
import machine
import process
import privateSchedule
import areaSchedule
import combinedSchedule
import optimize
import timeUtils

# This API is intended to be an asbtraction between the backend and the GUI #
#
# The GUI should only talk to GUIinstance and never touch the backend classes
# directly. GUIinstance holds no logic of its own, it only forwards calls to
# the backend and returns the values.
#
# Time is measured in quarters (15 min), see timeUtils.

class GUIinstance:

    def __init__(self, companyName: str, dataDirectory: str | Path | None = None):
        self.companyInstance = company.company(companyName)
        self.privateScheduleInstance = privateSchedule.schedule()
        self.areaScheduleInstance = areaSchedule.schedule(dataDirectory)
        # The schedule checks processes against the company's working hours
        self.privateScheduleInstance.workingHours = self.companyInstance.workingHours
        self.combinedScheduleInstance = combinedSchedule.schedule(
            self.areaScheduleInstance, self.privateScheduleInstance
        )

    # ---------------------------- Company ---------------------------- #

    def getCompanyName(self) -> str:
        return self.companyInstance.getName()

    def setCompanyName(self, companyName: str):
        self.companyInstance.setName(companyName)

    # ------------------------- Working hours ------------------------- #

    def getWorkingHours(self) -> dict:
        return self.companyInstance.workingHours.toDict()

    def setWorkingHours(self, start: str, end: str,
                        lunchStart: str | None = None,
                        lunchEnd: str | None = None) -> list[int]:
        """Times as 'HH:MM' ('24:00' for midnight), lunch may be None.
        Returns ids of processes that now run outside the working hours."""
        def index(time):
            return None if time is None else timeUtils.timeToIndex(time)
        self.companyInstance.workingHours.set(index(start), index(end),
                                              index(lunchStart), index(lunchEnd))
        return [b["id"] for b in self.getProcessBlocks() if b["outsideHours"]]

    # ---------------------------- Machines --------------------------- #

    def addMachine(self, name: str, kilowattage: int) -> dict:
        newMachine = machine.machine(kilowattage, name)
        self.companyInstance.addMachine(newMachine)
        return newMachine.toDict()

    def removeMachine(self, name: str):
        self.companyInstance.removeMachine(name)

    def editMachine(self, name: str, newName: str | None = None,
                    newKilowattage: int | None = None) -> dict:
        return self.companyInstance.editMachine(name, newName, newKilowattage).toDict()

    def getMachines(self) -> list[dict]:
        return self.companyInstance.getMachinesInfo()

    def getMachine(self, name: str) -> dict:
        return self.companyInstance.getMachine(name).toDict()

    # ------------------------ Private schedule ----------------------- #
    # Methods marked TODO call privateSchedule/process methods that do not
    # exist yet.

    def addProcess(self, machineName: str, durationQuarters: int, startIndex: int):
        targetMachine = self.companyInstance.getMachine(machineName)
        newProcess = process.process(targetMachine, durationQuarters)
        return self.privateScheduleInstance.addProcess(newProcess, startIndex)

    def removeProcess(self, processId: int):
        return self.combinedScheduleInstance.removeProcess(processId)

    def moveProcess(self, processId: int, newStartIndex: int) -> dict:
        return self.combinedScheduleInstance.moveProcess(processId, newStartIndex)

    def setProcessDependencies(self, processId: int, dependencyIds: list[int]) -> list[int]:
        """processId may only start once every process in dependencyIds has
        finished. An empty list makes it independent. Returns the ids of
        processes that were pushed later to respect the new order."""
        return self.combinedScheduleInstance.setDependencies(processId, dependencyIds)

    def setProcessDuration(self, processId: int, durationQuarters: int):
        # TODO: privateSchedule.setProcessDuration
        return self.privateScheduleInstance.setProcessDuration(processId, durationQuarters)

    def getProcesses(self) -> list[dict]:
        # TODO: privateSchedule.getProcesses
        return self.privateScheduleInstance.getProcesses()

    def clearSchedule(self):
        # TODO: privateSchedule.clear
        return self.privateScheduleInstance.clear()

    def setMaxCapacity(self, maxKW: float | None):
        self.privateScheduleInstance.maxCap = maxKW

    def getMaxCapacity(self) -> int | None:
        return self.privateScheduleInstance.maxCap

    def getPowerAtIndex(self, index: int) -> int:
        return self.privateScheduleInstance.getTotalPowerAtIndex(index)

    def getPrivateLoadProfile(self) -> list[float]:
        return self.combinedScheduleInstance.getPrivateProfile()

    def getProcessBlocks(self) -> list[dict]:
        return self.combinedScheduleInstance.getProcessBlocks()

    # ------------------------- Area forecast ------------------------- #

    def loadAreaData(self):
        self.areaScheduleInstance.importJsonFiles()

    def loadAreaFile(self, filePath: str | Path):
        self.areaScheduleInstance.importJsonFile(filePath)

    def getAvailableHorizons(self) -> list[str]:
        return self.areaScheduleInstance.getHorizons()

    def getAvailableDates(self, horizon: str | None = None) -> list[str]:
        return self.areaScheduleInstance.getDates(horizon)

    def getAreaForecast(self, date: str | datetime.date,
                        horizon: str | None = None) -> list[float]:
        return self.areaScheduleInstance.getDay(date, horizon)

    # ------------------------- Combined view ------------------------- #

    def getCombinedProfile(self, date: str | datetime.date,
                           horizon: str | None = None) -> list[dict]:
        return self.combinedScheduleInstance.getCombinedProfile(date, horizon)

    def getCapacityViolations(self, date: str | datetime.date,
                              horizon: str | None = None) -> list[dict]:
        return self.combinedScheduleInstance.getCapacityViolations(date, horizon)

    def getDaySummary(self, date: str | datetime.date,
                      horizon: str | None = None) -> dict:
        return self.combinedScheduleInstance.getDaySummary(date, horizon)

    # --------------------------- Optimiser --------------------------- #

    def optimizeSchedule(self, date: str | datetime.date,
                         horizon: str | None = None) -> dict:
        """Moves the processes to lower the day's peak power.
        Returns the day summary before and after."""
        before = self.getDaySummary(date, horizon)
        optimizer = optimize.optimize(self.privateScheduleInstance,
                                      self.areaScheduleInstance,
                                      self.companyInstance)
        optimizer.optimize_schedule(date, horizon)
        return {"before": before, "after": self.getDaySummary(date, horizon)}

    def getOptimFlex(self) -> int:
        return self.companyInstance.maxOptimFlex

    def setOptimFlex(self, quarters: int):
        if quarters < 0:
            raise ValueError("Flex must be zero or more quarters")
        self.companyInstance.maxOptimFlex = int(quarters)

    # ---------------------------- Helpers ---------------------------- #

    @staticmethod
    def indexToTime(index: int) -> str:
        return timeUtils.indexToTime(index)

    @staticmethod
    def timeToIndex(time: str) -> int:
        return timeUtils.timeToIndex(time)
