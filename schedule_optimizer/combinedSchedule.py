import datetime

import areaSchedule
import privateSchedule
import timeUtils

# Combines the area forecast with the company's own schedule. #
class schedule:
    def __init__ (self, area: areaSchedule.schedule,
                  private: privateSchedule.schedule):
        self.area = area
        self.private = private

    def getPrivateProfile(self) -> list[float]:
        """Power (kW) used by the company's own processes for every quarter of the day."""
        return [self.private.getTotalPowerAtIndex(i)
                for i in range(timeUtils.QUARTERS_PER_DAY)]

    def getCombinedProfile(self, date: str | datetime.date,
                           horizon: str | None = None) -> list[dict]:
        """Area forecast and company load side by side, one row per quarter."""
        areaValues = self.area.getDay(date, horizon)
        maxCap = self.private.maxCap

        rows = []
        for i, areaKW in enumerate(areaValues):
            privateKW = self.private.getTotalPowerAtIndex(i)
            totalKW = areaKW + privateKW
            rows.append({
                "index": i,
                "time": timeUtils.indexToTime(i),
                "areaKW": areaKW,
                "privateKW": privateKW,
                "totalKW": totalKW,
                "overCapacity": maxCap is not None and totalKW > maxCap,
            })
        return rows

    def getCapacityViolations(self, date: str | datetime.date,
                              horizon: str | None = None) -> list[dict]:
        """Quarters where total power is above the max capacity."""
        return [row for row in self.getCombinedProfile(date, horizon)
                if row["overCapacity"]]

    def getDaySummary(self, date: str | datetime.date,
                      horizon: str | None = None) -> dict:
        profile = self.getCombinedProfile(date, horizon)
        peak = max(profile, key=lambda r: r["totalKW"])
        return {
            "date": str(date),
            "horizon": horizon,
            "processCount": len(self.private.processTimeline),
            "maxCapacityKW": self.private.maxCap,
            "peakTotalKW": peak["totalKW"],
            "peakTime": peak["time"],
            "areaEnergyKWh": sum(r["areaKW"] for r in profile) * timeUtils.HOURS_PER_QUARTER,
            "privateEnergyKWh": sum(r["privateKW"] for r in profile) * timeUtils.HOURS_PER_QUARTER,
            "violationCount": sum(1 for r in profile if r["overCapacity"]),
        }
