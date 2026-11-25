import unittest

import company
import machine
import optimize
import privateSchedule
import process
import workingHours


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


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.machine_a = machine.machine(10, "A")
        self.machine_b = machine.machine(10, "B")
        self.company = company.company("company")
        self.company.addMachine(self.machine_a)
        self.company.addMachine(self.machine_b)
        self.schedule = privateSchedule.schedule()

    def add(self, machine_instance, duration, start):
        new_process = process.process(machine_instance, duration)
        self.schedule.addProcess(new_process, start)
        return new_process

    def test_cycles_and_self_dependencies_are_rejected(self):
        a = self.add(self.machine_a, 2, 0)
        b = self.add(self.machine_b, 2, 2)
        self.schedule.setDependencies(b, [a])
        with self.assertRaises(ValueError):
            self.schedule.setDependencies(a, [b])
        with self.assertRaises(ValueError):
            self.schedule.setDependencies(a, [a])
        self.assertEqual(a.dependencies, [])

    def test_setting_a_dependency_pushes_the_chain_later(self):
        a = self.add(self.machine_a, 4, 10)
        b = self.add(self.machine_b, 2, 8)
        c = self.add(self.machine_b, 2, 9)
        self.schedule.setDependencies(c, [b])
        self.schedule.setDependencies(b, [a])
        self.assertEqual(self.schedule.getStart(b), 14)
        self.assertEqual(self.schedule.getStart(c), 16)
        self.assertEqual(self.schedule.getDependencyViolations(), [])

    def test_dependency_that_does_not_fit_in_the_day_changes_nothing(self):
        a = self.add(self.machine_a, 50, 40)
        b = self.add(self.machine_b, 10, 0)
        with self.assertRaises(ValueError):
            self.schedule.setDependencies(b, [a])
        self.assertEqual(b.dependencies, [])
        self.assertEqual(self.schedule.getStart(b), 0)

    def test_moves_that_break_the_order_are_refused(self):
        a = self.add(self.machine_a, 4, 10)
        b = self.add(self.machine_b, 2, 14)
        self.schedule.setDependencies(b, [a])
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(b, 13)
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(a, 11)
        self.schedule.moveProcess(b, 20)
        self.schedule.moveProcess(a, 16)
        self.assertEqual(self.schedule.getStart(a), 16)

    def test_removing_a_process_drops_it_as_a_dependency(self):
        a = self.add(self.machine_a, 2, 0)
        b = self.add(self.machine_b, 2, 2)
        self.schedule.setDependencies(b, [a])
        self.schedule.removeProcess(a)
        self.assertTrue(b.isIndependent())

    def test_multiple_dependencies(self):
        a = self.add(self.machine_a, 4, 0)
        b = self.add(self.machine_b, 6, 0)
        c = self.add(self.machine_a, 2, 0)
        self.schedule.setDependencies(c, [a, b])
        self.assertEqual(self.schedule.getStart(c), 6)

    def test_optimizer_keeps_dependent_after_its_dependency(self):
        # A peak at quarters 10-13 pushes both processes away from it.
        # Without the dependency B (independent) would move before A.
        area = [0.0] * 96
        area[10:14] = [100.0] * 4
        a = self.add(self.machine_a, 4, 10)
        b = self.add(self.machine_b, 4, 14)
        self.schedule.setDependencies(b, [a])
        self.company.maxOptimFlex = 8

        optimize.optimize(
            self.schedule, FakeAreaSchedule(area), self.company
        ).optimize_schedule("test-day")

        self.assertGreaterEqual(self.schedule.getStart(b), self.schedule.getEnd(a))
        self.assertEqual(self.schedule.getDependencyViolations(), [])
        peak = max(area[i] + self.schedule.getTotalPowerAtIndex(i) for i in range(96))
        self.assertEqual(peak, 100.0)

    def test_optimizer_respects_fixed_dependency(self):
        # Fixed process (machine not owned by company) ends at quarter 20.
        # Moving the dependent to quarter 14 would lower the peak, but it
        # has to wait for the fixed process, so it stays at 20.
        foreign = machine.machine(5, "foreign")
        fixed = self.add(foreign, 4, 16)
        area = [0.0] * 96
        area[20:30] = [8.0] * 10
        self.company.maxOptimFlex = 8

        independent = self.add(self.machine_a, 2, 20)
        optimize.optimize(
            self.schedule, FakeAreaSchedule(area), self.company
        ).optimize_schedule("test-day")
        self.assertLess(self.schedule.getStart(independent), 20)
        self.schedule.removeProcess(independent)

        movable = self.add(self.machine_a, 2, 20)
        self.schedule.setDependencies(movable, [fixed])
        optimize.optimize(
            self.schedule, FakeAreaSchedule(area), self.company
        ).optimize_schedule("test-day")

        self.assertEqual(self.schedule.getStart(fixed), 16)
        self.assertEqual(self.schedule.getStart(movable), 20)

    def test_optimizer_reports_infeasible_dependencies(self):
        foreign = machine.machine(5, "foreign")
        fixed = self.add(foreign, 4, 40)
        movable = self.add(self.machine_a, 2, 0)
        movable.addDependency(fixed)  # bypasses the push, schedule now broken
        self.company.maxOptimFlex = 4
        with self.assertRaises(RuntimeError):
            optimize.optimize(
                self.schedule, FakeAreaSchedule([0.0] * 96), self.company
            ).optimize_schedule("test-day")


class WorkingHoursTests(unittest.TestCase):
    def setUp(self):
        self.machine = machine.machine(10, "A")
        self.company = company.company("company")
        self.company.addMachine(self.machine)
        self.schedule = privateSchedule.schedule()
        self.schedule.workingHours = self.company.workingHours
        # 07:00-16:00 with lunch 12:00-13:00
        self.company.workingHours.set(28, 64, 48, 52)

    def test_invalid_hours_are_rejected(self):
        hours = workingHours.workingHours()
        for args in ((40, 30), (0, 97), (28, 64, 48, None), (28, 64, 20, 30),
                     (28, 64, 50, 48)):
            with self.assertRaises(ValueError):
                hours.set(*args)

    def test_processes_must_fit_inside_hours_and_avoid_lunch(self):
        with self.assertRaises(ValueError):
            self.schedule.addProcess(process.process(self.machine, 4), 26)  # before 07:00
        with self.assertRaises(ValueError):
            self.schedule.addProcess(process.process(self.machine, 4), 46)  # into lunch
        with self.assertRaises(ValueError):
            self.schedule.addProcess(process.process(self.machine, 4), 62)  # after 16:00
        p = process.process(self.machine, 4)
        self.schedule.addProcess(p, 44)  # 11:00-12:00, right up to lunch
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(p, 45)
        self.schedule.moveProcess(p, 52)  # right after lunch
        self.assertEqual(self.schedule.getStart(p), 52)

    def test_dependency_push_skips_lunch(self):
        a = process.process(self.machine, 4)
        b = process.process(self.machine, 4)
        self.schedule.addProcess(a, 44)  # ends 12:00 when lunch starts
        self.schedule.addProcess(b, 30)
        self.schedule.setDependencies(b, [a])
        self.assertEqual(self.schedule.getStart(b), 52)  # 13:00, after lunch

    def test_optimizer_keeps_processes_inside_hours(self):
        # The area load is high all afternoon, low during lunch and in the
        # evening. The optimizer must not use either.
        area = [0.0] * 96
        area[52:64] = [50.0] * 12
        p = process.process(self.machine, 4)
        self.schedule.addProcess(p, 56)
        self.company.maxOptimFlex = 16

        optimize.optimize(
            self.schedule, FakeAreaSchedule(area), self.company
        ).optimize_schedule("test-day")

        self.assertEqual(self.schedule.getWorkingHourViolations(), [])
        self.assertEqual(self.schedule.getStart(p), 44)  # 11:00-12:00

    def test_optimizer_moves_processes_back_inside_changed_hours(self):
        p = process.process(self.machine, 4)
        self.schedule.addProcess(p, 30)
        self.company.workingHours.set(32, 64)  # now opens at 08:00
        self.assertEqual(self.schedule.getWorkingHourViolations(), [p])
        optimize.optimize(
            self.schedule, FakeAreaSchedule([0.0] * 96), self.company
        ).optimize_schedule("test-day")
        self.assertEqual(self.schedule.getStart(p), 32)


if __name__ == "__main__":
    unittest.main()
