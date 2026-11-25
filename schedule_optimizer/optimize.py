from datetime import datetime

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

import areaSchedule
import company as company_module
import privateSchedule
import process as process_module


class optimize:
    def __init__(
        self,
        ownSchedule: privateSchedule.schedule,
        areaSchedule: areaSchedule.schedule,
        company: company_module.company | None = None,
    ):
        self.ownSchedule = ownSchedule
        self.areaSchedule = areaSchedule
        self.company = company

    def optimize_schedule(
        self,
        date: datetime | str | None = None,
        horizon: str | None = None,
    ):
        if self.company is None:
            raise ValueError("A company is required to identify movable processes")

        if date is None:
            if len(self.areaSchedule.timeLineTotal) != 1 or horizon is not None:
                raise ValueError(
                    "Provide a date when the area schedule contains zero or multiple days"
                )
            area_timeline = next(iter(self.areaSchedule.timeLineTotal.values()))
        else:
            area_timeline = self.areaSchedule.getDay(date, horizon)

        area_load = np.asarray(area_timeline, dtype=float)
        if area_load.shape != (96,) or not np.isfinite(area_load).all():
            raise ValueError("The area power timeline must contain 96 finite values")

        max_flex = self.company.maxOptimFlex
        if not isinstance(max_flex, int) or isinstance(max_flex, bool) or max_flex < 0:
            raise ValueError("company.maxOptimFlex must be a non-negative integer")

        company_machines = {id(machine) for machine in self.company.machineList}
        hours = getattr(self.company, "workingHours", None)
        movable_entries = []
        fixed_load = np.zeros(96, dtype=float)

        for entry in self.ownSchedule.processTimeline:
            scheduled_process = entry["process"]
            start = entry["startIndex"]
            duration = scheduled_process.getDurationQuarter()
            power = scheduled_process.machine.getKW()

            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(duration, int)
                or duration <= 0
                or start < 0
                or start + duration > 96
                or not np.isfinite(power)
                or power < 0
            ):
                raise ValueError("The private schedule contains an invalid process block")

            if id(scheduled_process.machine) in company_machines:
                # Only starts inside working hours (and outside lunch)
                candidates = [
                    candidate for candidate in range(
                        max(0, start - max_flex),
                        min(96 - duration, start + max_flex) + 1,
                    )
                    if hours is None or hours.allows(candidate, duration)
                ]
                movable_entries.append((entry, scheduled_process, start, power, duration, candidates))
            else:
                fixed_load[start : start + duration] += power

        if not movable_entries:
            return self.ownSchedule

        candidates_by_process = [list(item[5]) for item in movable_entries]
        order_pairs = self._apply_dependencies(movable_entries, candidates_by_process)

        base_load = area_load + fixed_load
        variable_count = sum(len(candidates) for candidates in candidates_by_process)
        peak_variable = variable_count
        row_indices = []
        column_indices = []
        coefficients = []
        lower_bounds = []
        upper_bounds = []

        variable = 0
        for process_index, candidates in enumerate(candidates_by_process):
            lower_bounds.append(1.0)
            upper_bounds.append(1.0)
            for start in candidates:
                row_indices.append(process_index)
                column_indices.append(variable)
                coefficients.append(1.0)

                _, _, _, power, duration, _ = movable_entries[process_index]
                for quarter in range(start, start + duration):
                    row_indices.append(len(movable_entries) + quarter)
                    column_indices.append(variable)
                    coefficients.append(power)
                variable += 1

        for quarter in range(96):
            lower_bounds.append(-np.inf)
            upper_bounds.append(-base_load[quarter])
            row_indices.append(len(movable_entries) + quarter)
            column_indices.append(peak_variable)
            coefficients.append(-1.0)

        # Order constraints between two movable processes:
        #   start(B) - end(A) >= 0
        #   sum(s * x_B,s) - sum((s + duration_A) * x_A,s) >= 0
        first_variable = []
        variable = 0
        for candidates in candidates_by_process:
            first_variable.append(variable)
            variable += len(candidates)

        order_row = len(movable_entries) + 96
        for dependent_index, dependency_index in order_pairs:
            dependency_duration = movable_entries[dependency_index][4]
            for offset, start in enumerate(candidates_by_process[dependent_index]):
                row_indices.append(order_row)
                column_indices.append(first_variable[dependent_index] + offset)
                coefficients.append(float(start))
            for offset, start in enumerate(candidates_by_process[dependency_index]):
                row_indices.append(order_row)
                column_indices.append(first_variable[dependency_index] + offset)
                coefficients.append(-float(start + dependency_duration))
            lower_bounds.append(0.0)
            upper_bounds.append(np.inf)
            order_row += 1

        constraints = LinearConstraint(
            coo_matrix(
                (coefficients, (row_indices, column_indices)),
                shape=(order_row, variable_count + 1),
            ).tocsr(),
            np.asarray(lower_bounds),
            np.asarray(upper_bounds),
        )
        integrality = np.zeros(variable_count + 1, dtype=int)
        integrality[:variable_count] = 1
        lower = np.zeros(variable_count + 1)
        upper = np.ones(variable_count + 1)
        upper[peak_variable] = np.inf
        objective = np.zeros(variable_count + 1)
        objective[peak_variable] = 1.0

        result = milp(
            objective,
            integrality=integrality,
            bounds=Bounds(lower, upper),
            constraints=constraints,
        )
        if not result.success:
            if result.status == 2:
                raise RuntimeError(
                    "No schedule satisfies the process dependencies within the "
                    "allowed shift. Allow a larger shift or move processes by hand."
                )
            raise RuntimeError(f"Schedule optimization failed: {result.message}")

        allowed_peak = result.x[peak_variable] + max(
            1e-7, abs(result.x[peak_variable]) * 1e-9
        )
        upper[peak_variable] = allowed_peak

        movement_cost = np.zeros(variable_count + 1)
        variable = 0
        candidate_indices = []
        for process_index, candidates in enumerate(candidates_by_process):
            original_start = movable_entries[process_index][2]
            for start in candidates:
                movement_cost[variable] = abs(start - original_start)
                candidate_indices.append((process_index, start, variable))
                variable += 1

        tie_break_result = milp(
            movement_cost,
            integrality=integrality,
            bounds=Bounds(lower, upper),
            constraints=constraints,
        )
        if not tie_break_result.success:
            raise RuntimeError(
                f"Schedule movement minimization failed: {tie_break_result.message}"
            )

        selected_starts = {}
        for process_index, start, candidate_index in candidate_indices:
            if tie_break_result.x[candidate_index] > 0.5:
                selected_starts[process_index] = start

        if len(selected_starts) != len(movable_entries):
            raise RuntimeError("Schedule optimizer returned an incomplete process placement")

        for process_index, (entry, scheduled_process, *_rest) in enumerate(movable_entries):
            new_start = selected_starts[process_index]
            if new_start != entry["startIndex"]:
                self.moveProcess(new_start, scheduled_process)

        return self.ownSchedule

    def _apply_dependencies(self, movable_entries, candidates_by_process):
        """Respects "B waits for A" (start(B) >= end(A)).

        A dependency on or of a fixed process only narrows the candidate
        starts of the movable one. Pairs where both can move are returned
        as (dependent index, dependency index) and become MILP constraints.
        """
        movable_index = {
            id(item[1]): index for index, item in enumerate(movable_entries)
        }
        fixed_start = {
            id(entry["process"]): entry["startIndex"]
            for entry in self.ownSchedule.processTimeline
            if id(entry["process"]) not in movable_index
        }
        order_pairs = []

        for entry in self.ownSchedule.processTimeline:
            dependent = entry["process"]
            for dependency in getattr(dependent, "dependencies", []):
                dependency_end = None
                if id(dependency) in fixed_start:
                    dependency_end = (
                        fixed_start[id(dependency)] + dependency.getDurationQuarter()
                    )
                elif id(dependency) not in movable_index:
                    continue  # dependency is not scheduled

                if id(dependent) in movable_index:
                    dependent_index = movable_index[id(dependent)]
                    if dependency_end is not None:
                        candidates_by_process[dependent_index] = [
                            start for start in candidates_by_process[dependent_index]
                            if start >= dependency_end
                        ]
                    else:
                        order_pairs.append(
                            (dependent_index, movable_index[id(dependency)])
                        )
                elif id(dependency) in movable_index:
                    dependency_index = movable_index[id(dependency)]
                    duration = dependency.getDurationQuarter()
                    dependent_start = fixed_start[id(dependent)]
                    candidates_by_process[dependency_index] = [
                        start for start in candidates_by_process[dependency_index]
                        if start + duration <= dependent_start
                    ]

        for index, candidates in enumerate(candidates_by_process):
            if not candidates:
                name = movable_entries[index][1].machine.name
                raise RuntimeError(
                    f"{name} cannot be placed inside the working hours and after "
                    "its dependencies within the allowed shift. Allow a larger "
                    "shift or move processes by hand."
                )
        return order_pairs

    def moveProcess(self, newIndex: int, scheduledProcess: process_module.process):
        if (
            not isinstance(newIndex, int)
            or isinstance(newIndex, bool)
            or newIndex < 0
            or newIndex + scheduledProcess.getDurationQuarter() > 96
        ):
            raise ValueError(
                "New index must be between 0 and 95 and leave the process within the day"
            )

        matching_entries = [
            entry
            for entry in self.ownSchedule.processTimeline
            if entry["process"] is scheduledProcess
        ]
        if len(matching_entries) != 1:
            raise ValueError("The stated process must appear exactly once in the schedule")

        matching_entries[0]["startIndex"] = newIndex
