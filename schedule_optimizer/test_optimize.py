import unittest

import company
import machine
import optimize
import privateSchedule
import process


class FakeAreaSchedule:
    def __init__(self, timeline):
        self.timeLineTotal = {"test-day": timeline}

    def getDay(self, date, horizon=None):
        return self.timeLineTotal[date]


class ScheduleOptimizerTests(unittest.TestCase):
    def test_move_process_updates_existing_entry(self):
        machine_instance = machine.machine(10, "owned")
        scheduled_process = process.process(machine_instance, 2)
        private_schedule = privateSchedule.schedule()
        private_schedule.addProcess(scheduled_process, 4)
        original_entry = private_schedule.processTimeline[0]
        optimizer = optimize.optimize(
            private_schedule, FakeAreaSchedule([0.0] * 96)
        )

        optimizer.moveProcess(7, scheduled_process)

        self.assertIs(private_schedule.processTimeline[0], original_entry)
        self.assertIs(original_entry["process"], scheduled_process)
        self.assertEqual(original_entry["startIndex"], 7)

    def test_optimization_reduces_peak_within_flex_and_keeps_other_blocks_fixed(self):
        owned_machine = machine.machine(10, "owned")
        other_machine = machine.machine(5, "other")
        company_instance = company.company("company")
        company_instance.addMachine(owned_machine)
        company_instance.maxOptimFlex = 2

        movable_process = process.process(owned_machine, 2)
        fixed_process = process.process(other_machine, 2)
        private_schedule = privateSchedule.schedule()
        private_schedule.addProcess(movable_process, 0)
        private_schedule.addProcess(fixed_process, 40)

        area_timeline = [0.0] * 96
        area_timeline[0:2] = [20.0, 20.0]
        area_schedule = FakeAreaSchedule(area_timeline)
        optimizer = optimize.optimize(
            private_schedule, area_schedule, company_instance
        )

        optimized_schedule = optimizer.optimize_schedule("test-day")

        self.assertIs(optimized_schedule, private_schedule)
        self.assertEqual(private_schedule.processTimeline[0]["startIndex"], 2)
        self.assertEqual(private_schedule.processTimeline[1]["startIndex"], 40)
        self.assertEqual(movable_process.getDurationQuarter(), 2)
        self.assertEqual(
            max(
                area_timeline[index]
                + private_schedule.getTotalPowerAtIndex(index)
                for index in range(96)
            ),
            20.0,
        )


if __name__ == "__main__":
    unittest.main()
