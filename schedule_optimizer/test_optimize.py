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
        c = self.add(self.machine_b, 2, 10)  # B is busy until 10
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
        c = self.add(self.machine_a, 2, 4)  # A is busy until 4
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


class OutsideHoursTests(unittest.TestCase):
    """Machines allowed to run outside the working hours must start inside
    them, but may then run through lunch and after closing."""

    def setUp(self):
        self.company = company.company("company")
        self.free = machine.machine(10, "free", allowOutsideHours=True)
        self.strict = machine.machine(10, "strict")
        self.company.addMachine(self.free)
        self.company.addMachine(self.strict)
        self.schedule = privateSchedule.schedule()
        self.schedule.workingHours = self.company.workingHours
        # 07:00-16:00 with lunch 12:00-13:00
        self.company.workingHours.set(28, 64, 48, 52)

    def test_allowed_machine_runs_through_lunch_and_past_closing(self):
        through_lunch = process.process(self.free, 4)
        self.schedule.addProcess(through_lunch, 46)    # 11:30-12:30
        past_closing = process.process(self.free, 8)
        self.schedule.addProcess(past_closing, 62)     # 15:30-17:30
        self.assertEqual(self.schedule.getWorkingHourViolations(), [])
        self.assertTrue(self.schedule.runsPastHours(past_closing, 62))

    def test_allowed_machine_must_still_start_within_hours(self):
        for start in (26, 48, 64):  # before opening, during lunch, at closing
            with self.assertRaises(ValueError):
                self.schedule.addProcess(process.process(self.free, 4), start)
        p = process.process(self.free, 4)
        self.schedule.addProcess(p, 60)
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(p, 66)
        with self.assertRaises(ValueError):   # still has to finish by 24:00
            self.schedule.moveProcess(p, 93)

    def test_other_machines_keep_to_the_hours(self):
        for start in (46, 62):
            with self.assertRaises(ValueError):
                self.schedule.addProcess(process.process(self.strict, 4), start)

    def test_turning_the_permission_off_flags_the_process(self):
        p = process.process(self.free, 8)
        self.schedule.addProcess(p, 62)
        self.company.editMachine("free", allowOutsideHours=False)
        self.assertEqual(self.schedule.getWorkingHourViolations(), [p])

    def _afternoon_peak(self):
        # The area load is high during all working quarters, low at lunch
        # and in the evening.
        area = [0.0] * 96
        area[28:48] = [50.0] * 20
        area[52:64] = [50.0] * 12
        return area

    def test_optimizer_lets_allowed_machine_run_past_closing(self):
        p = process.process(self.free, 8)
        self.schedule.addProcess(p, 56)   # 14:00-16:00
        self.company.maxOptimFlex = 16

        optimize.optimize(
            self.schedule, FakeAreaSchedule(self._afternoon_peak()), self.company
        ).optimize_schedule("test-day")

        # Latest start inside the hours: 15:45, then it runs on until 17:45
        self.assertEqual(self.schedule.getStart(p), 63)
        self.assertGreater(self.schedule.getEnd(p), 64)
        self.assertEqual(self.schedule.getWorkingHourViolations(), [])

    def test_optimizer_keeps_other_machines_inside_hours(self):
        p = process.process(self.strict, 8)
        self.schedule.addProcess(p, 56)
        self.company.maxOptimFlex = 16

        optimize.optimize(
            self.schedule, FakeAreaSchedule(self._afternoon_peak()), self.company
        ).optimize_schedule("test-day")

        self.assertEqual(self.schedule.getWorkingHourViolations(), [])
        self.assertLessEqual(self.schedule.getEnd(p), 64)


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.machine = machine.machine(10, "A")
        self.company = company.company("company")
        self.company.addMachine(self.machine)
        self.schedule = privateSchedule.schedule()

    def test_invalid_deadlines_are_rejected(self):
        for deadline in (0, 97, 3, True, 12.5):
            with self.assertRaises(ValueError):
                process.process(self.machine, 4, deadline)

    def test_processes_cannot_be_added_or_moved_past_their_deadline(self):
        with self.assertRaises(ValueError):
            self.schedule.addProcess(process.process(self.machine, 4, deadline=40), 37)
        p = process.process(self.machine, 4, deadline=40)
        self.schedule.addProcess(p, 36)          # ends exactly at the deadline
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(p, 37)
        self.schedule.moveProcess(p, 30)
        self.assertEqual(self.schedule.latestStart(p), 36)
        self.assertEqual(max(self.schedule.allowedStarts(p)), 36)

    def test_dependency_push_that_breaks_a_deadline_changes_nothing(self):
        other = machine.machine(10, "B")
        a = process.process(other, 4)
        b = process.process(self.machine, 4, deadline=12)
        self.schedule.addProcess(a, 10)   # ends at 14
        self.schedule.addProcess(b, 0)
        with self.assertRaises(ValueError):
            self.schedule.setDependencies(b, [a])
        self.assertEqual(self.schedule.getStart(b), 0)
        self.assertEqual(b.dependencies, [])

    def _optimize(self, area):
        optimize.optimize(
            self.schedule, FakeAreaSchedule(area), self.company
        ).optimize_schedule("test-day")

    def test_optimizer_keeps_processes_before_their_deadline(self):
        # High load early in the day: the process would like to move to 14
        area = [0.0] * 96
        area[2:14] = [100.0] * 12
        self.company.maxOptimFlex = 8

        free = process.process(self.machine, 4)
        self.schedule.addProcess(free, 10)
        self._optimize(area)
        self.assertEqual(self.schedule.getStart(free), 14)
        self.schedule.removeProcess(free)

        due = process.process(self.machine, 4, deadline=16)
        self.schedule.addProcess(due, 10)
        self._optimize(area)
        self.assertEqual(self.schedule.getStart(due), 12)   # 12-16, just in time
        self.assertEqual(self.schedule.getDeadlineViolations(), [])

    def test_optimizer_moves_a_late_process_before_its_deadline(self):
        p = process.process(self.machine, 4)
        self.schedule.addProcess(p, 20)
        p.setDeadline(22)                  # set after scheduling: now late
        self.assertEqual(self.schedule.getDeadlineViolations(), [p])
        self._optimize([0.0] * 96)
        self.assertEqual(self.schedule.getStart(p), 18)
        self.assertEqual(self.schedule.getDeadlineViolations(), [])

    def test_optimizer_reports_a_deadline_it_cannot_meet(self):
        p = process.process(self.machine, 4)
        self.schedule.addProcess(p, 40)
        p.setDeadline(20)
        self.company.maxOptimFlex = 4
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            self._optimize([0.0] * 96)
        self.assertEqual(self.schedule.getStart(p), 40)


class MachineOverlapTests(unittest.TestCase):
    """A machine instance runs one process at a time."""

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

    def test_overlapping_processes_on_one_machine_are_refused(self):
        a = self.add(self.machine_a, 4, 10)
        with self.assertRaises(ValueError):
            self.add(self.machine_a, 4, 12)
        with self.assertRaises(ValueError):
            self.add(self.machine_a, 4, 8)
        self.add(self.machine_a, 2, 8)           # ends right when a starts
        b = self.add(self.machine_a, 4, 14)      # right after a
        self.add(self.machine_b, 4, 12)          # another machine is free
        with self.assertRaises(ValueError):
            self.schedule.moveProcess(b, 13)
        self.assertNotIn(12, self.schedule.allowedStarts(b))
        self.assertEqual(self.schedule.getStart(a), 10)
        self.assertEqual(self.schedule.getOverlapViolations(), [])

    def test_dependency_push_skips_time_the_machine_is_busy(self):
        a = self.add(self.machine_a, 4, 10)      # ends at 14
        self.add(self.machine_b, 4, 16)          # B busy 16-20
        b = self.add(self.machine_b, 4, 0)
        self.schedule.setDependencies(b, [a])
        self.assertEqual(self.schedule.getStart(b), 20)
        self.assertEqual(self.schedule.getOverlapViolations(), [])

    def test_overlaps_made_by_hand_are_reported(self):
        a = self.add(self.machine_a, 4, 10)
        b = process.process(self.machine_a, 4)
        self.schedule.processTimeline.append({"startIndex": 12, "process": b})
        self.assertEqual(self.schedule.getOverlapViolations(), [(a, b)])

    def _valley_area(self):
        area = [100.0] * 96
        area[20:24] = [0.0] * 4
        return area

    def _optimize(self):
        optimize.optimize(
            self.schedule, FakeAreaSchedule(self._valley_area()), self.company
        ).optimize_schedule("test-day")

    def test_optimizer_uses_the_valley_for_two_machines(self):
        a = self.add(self.machine_a, 4, 16)
        b = self.add(self.machine_b, 4, 24)
        self._optimize()
        self.assertEqual(self.schedule.getStart(a), 20)
        self.assertEqual(self.schedule.getStart(b), 20)

    def test_optimizer_never_runs_two_processes_on_one_machine(self):
        # Both want the valley at 20-24, but they share machine A. Running
        # both in it would give a peak of 100 kW, one at a time gives 110.
        self.add(self.machine_a, 4, 16)
        self.add(self.machine_a, 4, 24)
        self._optimize()
        self.assertEqual(self.schedule.getOverlapViolations(), [])
        area = self._valley_area()
        peak = max(area[i] + self.schedule.getTotalPowerAtIndex(i) for i in range(96))
        self.assertEqual(peak, 110.0)
        # The valley is still used as well as it can be
        self.assertEqual([self.schedule.getTotalPowerAtIndex(i) for i in range(20, 24)],
                         [10.0] * 4)

    def test_optimizer_fixes_an_existing_overlap(self):
        a = self.add(self.machine_a, 4, 30)
        b = process.process(self.machine_a, 4)
        self.schedule.processTimeline.append({"startIndex": 32, "process": b})
        optimize.optimize(
            self.schedule, FakeAreaSchedule([0.0] * 96), self.company
        ).optimize_schedule("test-day")
        self.assertEqual(self.schedule.getOverlapViolations(), [])
        self.assertTrue(self.schedule.getEnd(a) <= self.schedule.getStart(b)
                        or self.schedule.getEnd(b) <= self.schedule.getStart(a))

    def test_optimizer_refuses_overlapping_fixed_processes(self):
        foreign = machine.machine(5, "foreign")
        self.schedule.processTimeline += [
            {"startIndex": 10, "process": process.process(foreign, 4)},
            {"startIndex": 12, "process": process.process(foreign, 4)},
        ]
        with self.assertRaisesRegex(RuntimeError, "same time"):
            self._optimize()

    def test_conflicting_constraints_are_reported(self):
        # The factory opens at 04:00 and both processes on A have to be
        # finished by 05:00, so both can only run 04:00-05:00.
        self.schedule.workingHours = self.company.workingHours
        self.company.workingHours.set(16, 96)
        first = process.process(self.machine_a, 4, deadline=20)
        self.schedule.addProcess(first, 16)
        second = self.add(self.machine_a, 4, 20)
        second.setDeadline(20)                     # late, has to move
        with self.assertRaisesRegex(RuntimeError, "machine availability"):
            self._optimize()
        self.assertEqual(self.schedule.getStart(first), 16)
        self.assertEqual(self.schedule.getStart(second), 20)


if __name__ == "__main__":
    unittest.main()
