import json
import tempfile
import unittest
from pathlib import Path

from GUI import peakChangeText
from InterfaceGUI import GUIinstance

DATE = "2023-01-01"
HORIZON = "48h"


def writeForecast(directory: str, values: list[float]):
    timestamps = {f"{DATE}T{q // 4:02d}:{q % 4 * 15:02d}:00": value
                  for q, value in enumerate(values)}
    Path(directory, "forecast.json").write_text(json.dumps({HORIZON: timestamps}))


class OptimizationPreviewTests(unittest.TestCase):
    """Optimize -> proposal (nothing moves) -> accept or reject.

    The area load falls from 70 kW at 07:30 towards the evening, so the
    50 kW process at 10:00 always wants to move later. With a max shift of
    2 quarters every proposal can move it at most to 10:30."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        area = [0.0] * 96
        for q in range(30, 61):
            area[q] = 100.0 - q
        writeForecast(self.tmp.name, area)

        self.gui = GUIinstance("test", self.tmp.name)
        self.gui.loadAreaData()
        self.gui.addMachine("Press", 50)
        self.gui.addProcess("Press", 4, 40)          # 10:00-11:00, peak 110 kW
        self.gui.setOptimFlex(2)

    def start(self, processId: int = 0) -> int:
        return self.gui.combinedScheduleInstance.getBlock(processId)["startIndex"]

    def preview(self) -> dict:
        return self.gui.previewOptimization(DATE, HORIZON)

    def test_preview_leaves_the_schedule_unchanged(self):
        proposal = self.preview()
        self.assertEqual(self.start(), 40)
        self.assertEqual(self.gui.getDaySummary(DATE, HORIZON)["peakTotalKW"], 110.0)
        [ghost] = proposal["blocks"]
        self.assertEqual((ghost["id"], ghost["fromStartIndex"], ghost["startIndex"]),
                         (0, 40, 42))
        self.assertEqual(ghost["shift"], 2)
        self.assertEqual(proposal["before"]["peakTotalKW"], 110.0)
        self.assertEqual(proposal["after"]["peakTotalKW"], 108.0)
        self.assertAlmostEqual(proposal["peakReductionKW"], 2.0)

    def test_repeated_previews_never_exceed_the_max_shift(self):
        for _ in range(4):
            proposal = self.preview()
            self.assertEqual(proposal["blocks"][0]["startIndex"], 42)
            self.assertEqual(self.start(), 40)

    def test_accepting_moves_the_processes_and_updates_the_peak(self):
        proposal = self.preview()
        result = self.gui.acceptOptimization()
        self.assertEqual(self.start(), 42)
        self.assertIsNone(self.gui.getOptimizationPreview(DATE, HORIZON))
        self.assertEqual(result["movedIds"], proposal["movedIds"])
        self.assertEqual(self.gui.getDaySummary(DATE, HORIZON)["peakTotalKW"],
                         proposal["after"]["peakTotalKW"])

    def test_after_accepting_the_next_shift_starts_from_the_new_schedule(self):
        self.preview()
        self.gui.acceptOptimization()
        self.assertEqual(self.preview()["blocks"][0]["startIndex"], 44)
        self.assertEqual(self.start(), 42)

    def test_rejecting_changes_nothing(self):
        self.preview()
        self.gui.rejectOptimization()
        self.assertEqual(self.start(), 40)
        self.assertIsNone(self.gui.getOptimizationPreview(DATE, HORIZON))
        with self.assertRaises(ValueError):
            self.gui.acceptOptimization()
        self.assertEqual(self.start(), 40)

    def test_changing_the_schedule_drops_the_proposal(self):
        changes = [
            lambda: self.gui.moveProcess(0, 39),
            lambda: self.gui.addProcess("Press", 2, 60),
            lambda: self.gui.setProcessDeadline(0, "20:00"),
            lambda: self.gui.setProcessDependencies(0, []),
            lambda: self.gui.setWorkingHours("00:00", "24:00"),
            lambda: self.gui.setMachineAllowOutsideHours("Press", True),
        ]
        for change in changes:
            self.preview()
            change()
            self.assertIsNone(self.gui.getOptimizationPreview(DATE, HORIZON))
            with self.assertRaises(ValueError):
                self.gui.acceptOptimization()

    def test_a_proposal_for_a_changed_schedule_is_never_applied(self):
        self.preview()
        # Changed behind the API's back
        self.gui.privateScheduleInstance.processTimeline[0]["startIndex"] = 38
        with self.assertRaises(ValueError):
            self.gui.acceptOptimization()
        self.assertEqual(self.start(), 38)

    def test_a_proposal_only_belongs_to_its_day(self):
        self.preview()
        self.assertIsNone(self.gui.getOptimizationPreview("2023-01-02", HORIZON))
        self.assertIsNotNone(self.gui.getOptimizationPreview(DATE, HORIZON))

    def test_no_improvement_gives_an_empty_proposal(self):
        self.gui.setOptimFlex(0)
        proposal = self.preview()
        self.assertEqual(proposal["blocks"], [])
        self.assertEqual(proposal["peakReductionKW"], 0.0)

    def test_infeasible_optimisation_changes_nothing(self):
        self.gui.setProcessDeadline(0, "09:00")   # ends 11:00, 2 quarters shift
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            self.preview()
        self.assertEqual(self.start(), 40)
        self.assertIsNone(self.gui.getOptimizationPreview(DATE, HORIZON))

    def test_proposal_keeps_one_process_per_machine_and_deadlines(self):
        self.gui.addProcess("Press", 4, 44, self.gui.timeToIndex("12:00"))
        self.gui.setOptimFlex(8)
        proposal = self.preview()
        self.assertTrue(proposal["blocks"])
        proposed = {b["id"]: b for b in proposal["blocks"]}
        starts = sorted(proposed.get(i, self.gui.combinedScheduleInstance.getBlock(i))
                        ["startIndex"] for i in (0, 1))
        self.assertGreaterEqual(starts[1], starts[0] + 4)
        self.assertLessEqual(proposed.get(1, {"endIndex": 48})["endIndex"], 48)
        self.gui.acceptOptimization()
        violations = self.gui.getScheduleViolations()
        self.assertEqual(violations["overlaps"], [])
        self.assertEqual(violations["lateForDeadline"], [])

    def test_optimize_schedule_still_applies_directly(self):
        result = self.gui.optimizeSchedule(DATE, HORIZON)
        self.assertEqual(self.start(), 42)
        self.assertEqual(result["before"]["peakTotalKW"], 110.0)
        self.assertEqual(result["after"]["peakTotalKW"], 108.0)


class PeakChangeTextTests(unittest.TestCase):
    def test_a_reduction_is_green(self):
        self.assertEqual(peakChangeText(12.34, proposed=True),
                         ("−12.3 kW proposed", "Gain.TLabel"))
        self.assertEqual(peakChangeText(2.0, proposed=False),
                         ("−2.0 kW optimised", "Gain.TLabel"))

    def test_no_reduction_is_neutral(self):
        for value in (0.0, 0.04, -0.04, 1e-9):
            self.assertEqual(peakChangeText(value, proposed=True),
                             ("No peak reduction", "StatName.TLabel"))

    def test_a_higher_peak_is_red(self):
        self.assertEqual(peakChangeText(-3.0, proposed=True),
                         ("+3.0 kW proposed", "Loss.TLabel"))


if __name__ == "__main__":
    unittest.main()
