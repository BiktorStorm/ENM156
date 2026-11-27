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
            options={"mip_rel_gap": 1e-9},
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

        movement_cost = np.zeros(variable_count, dtype=float)
        variable = 0
        candidate_indices = []
        for process_index, candidates in enumerate(candidates_by_process):
            original_start = movable_entries[process_index][2]
            for start in candidates:
                movement_cost[variable] = abs(start - original_start)
                candidate_indices.append((process_index, start, variable))
                variable += 1

        final_x = self._optimize_average_and_movement(
            movable_entries=movable_entries,
            candidates_by_process=candidates_by_process,
            order_pairs=order_pairs,
            base_load=base_load,
            allowed_peak=allowed_peak,
            movement_cost=movement_cost,
            base_constraints=constraints,
            base_integrality=integrality,
            base_lower=lower,
            base_upper=upper,
        )

        selected_starts = {}
        for process_index, start, candidate_index in candidate_indices:
            if final_x[candidate_index] > 0.5:
                selected_starts[process_index] = start

        if len(selected_starts) != len(movable_entries):
            raise RuntimeError("Schedule optimizer returned an incomplete process placement")

        for process_index, (entry, scheduled_process, *_rest) in enumerate(movable_entries):
            new_start = selected_starts[process_index]
            if new_start != entry["startIndex"]:
                self.moveProcess(new_start, scheduled_process)

        return self.ownSchedule

    def _optimize_average_and_movement(
        self,
        movable_entries,
        candidates_by_process,
        order_pairs,
        base_load: np.ndarray,
        allowed_peak: float,
        movement_cost: np.ndarray,
        base_constraints: LinearConstraint,
        base_integrality: np.ndarray,
        base_lower: np.ndarray,
        base_upper: np.ndarray,
    ) -> np.ndarray:
        """Minimizes load deviation from the daily average, then schedule movement.

        Because each process has fixed power and duration, the 24-hour mean
        load is invariant to shifting processes. Minimizing the sum of squared
        deviations sum((L_q - mean)^2) flattens the load curve around the daily
        average (filling valleys and avoiding secondary peaks) without ever
        worsening the optimal peak found in stage 1.
        """
        variable_count = len(movement_cost)
        total_movable_energy = sum(
            power * duration for _, _, _, power, duration, _ in movable_entries
        )
        mean_load = float(np.sum(base_load) + total_movable_energy) / 96.0

        # Identify quarters whose total load can vary across candidate starts.
        unconstrained_min = base_load.copy()
        unconstrained_max = base_load.copy()
        for process_index, candidates in enumerate(candidates_by_process):
            _, _, _, power, duration, _ = movable_entries[process_index]
            if power == 0:
                continue
            coverage_counts = np.zeros(96, dtype=int)
            for start in candidates:
                coverage_counts[start : start + duration] += 1
            num_candidates = len(candidates)
            unconstrained_min[coverage_counts == num_candidates] += power
            unconstrained_max[coverage_counts > 0] += power

        # Partition quarters into:
        # - variable_quarters: load can genuinely vary under the stage-1 peak cap
        # - pinned_quarters: load could exceed the peak cap without the constraint,
        #   so the peak cap pins their load to unconstrained_min[q]
        variable_quarters = []
        pinned_quarters = []
        variable_load_bounds = {}
        for quarter in range(96):
            if unconstrained_max[quarter] - unconstrained_min[quarter] <= 1e-9:
                continue
            l_min = float(unconstrained_min[quarter])
            l_max = max(l_min, min(float(allowed_peak), float(unconstrained_max[quarter])))
            if l_max - l_min > 1e-5 * max(1.0, abs(l_min)):
                variable_quarters.append(quarter)
                variable_load_bounds[quarter] = (l_min, l_max)
            else:
                pinned_quarters.append(quarter)

        if not variable_quarters:
            tie_break_objective = np.zeros(variable_count + 1, dtype=float)
            tie_break_objective[:variable_count] = movement_cost
            tie_break_result = milp(
                tie_break_objective,
                integrality=base_integrality,
                bounds=Bounds(base_lower, base_upper),
                constraints=base_constraints,
                options={"mip_rel_gap": 1e-9},
            )
            if not tie_break_result.success:
                raise RuntimeError(
                    f"Schedule movement minimization failed: {tie_break_result.message}"
                )
            return tie_break_result.x

        scale = max(
            max(abs(l_min - mean_load), abs(l_max - mean_load))
            for l_min, l_max in variable_load_bounds.values()
        )
        if scale <= 1e-12:
            scale = 1.0

        num_active = len(variable_quarters)
        quarter_to_active = {quarter: idx for idx, quarter in enumerate(variable_quarters)}
        quarter_to_pinned = {quarter: idx for idx, quarter in enumerate(pinned_quarters)}
        dev_var_offset = variable_count
        sq_var_offset = variable_count + num_active
        total_vars = variable_count + 2 * num_active

        row_indices = []
        column_indices = []
        coefficients = []
        lower_bounds = []
        upper_bounds = []

        pinned_row_offset = len(movable_entries) + num_active

        # 1. One start per movable process.
        # 2. Scaled deviation definition for variable quarters:
        #    sum(P_p / scale * x_{p,s}) - d_q = (mean_load - base_load[q]) / scale
        # 3. Direct peak-cap constraint for pinned quarters:
        #    sum(P_p * x_{p,s}) <= allowed_peak - base_load[q]
        variable = 0
        for process_index, candidates in enumerate(candidates_by_process):
            lower_bounds.append(1.0)
            upper_bounds.append(1.0)
            _, _, _, power, duration, _ = movable_entries[process_index]
            scaled_power = power / scale
            for start in candidates:
                row_indices.append(process_index)
                column_indices.append(variable)
                coefficients.append(1.0)

                if power > 0:
                    for quarter in range(start, start + duration):
                        active_idx = quarter_to_active.get(quarter)
                        if active_idx is not None:
                            row_indices.append(len(movable_entries) + active_idx)
                            column_indices.append(variable)
                            coefficients.append(scaled_power)
                        else:
                            pinned_idx = quarter_to_pinned.get(quarter)
                            if pinned_idx is not None:
                                row_indices.append(pinned_row_offset + pinned_idx)
                                column_indices.append(variable)
                                coefficients.append(power)
                variable += 1

        for active_idx, quarter in enumerate(variable_quarters):
            row = len(movable_entries) + active_idx
            rhs = (mean_load - base_load[quarter]) / scale
            lower_bounds.append(rhs)
            upper_bounds.append(rhs)
            row_indices.append(row)
            column_indices.append(dev_var_offset + active_idx)
            coefficients.append(-1.0)

        for quarter in pinned_quarters:
            lower_bounds.append(-np.inf)
            upper_bounds.append(float(allowed_peak - base_load[quarter]))

        # 4. Order constraints between movable processes.
        first_variable = []
        variable = 0
        for candidates in candidates_by_process:
            first_variable.append(variable)
            variable += len(candidates)

        next_row = pinned_row_offset + len(pinned_quarters)
        for dependent_index, dependency_index in order_pairs:
            dependency_duration = movable_entries[dependency_index][4]
            for offset, start in enumerate(candidates_by_process[dependent_index]):
                row_indices.append(next_row)
                column_indices.append(first_variable[dependent_index] + offset)
                coefficients.append(float(start))
            for offset, start in enumerate(candidates_by_process[dependency_index]):
                row_indices.append(next_row)
                column_indices.append(first_variable[dependency_index] + offset)
                coefficients.append(-float(start + dependency_duration))
            lower_bounds.append(0.0)
            upper_bounds.append(np.inf)
            next_row += 1

        # 5. Variable bounds: d_q in [(l_min - mean)/scale, (l_max - mean)/scale]
        #    enforces the stage-1 peak cap L_q <= allowed_peak on every variable quarter.
        integrality = np.zeros(total_vars, dtype=int)
        integrality[:variable_count] = 1
        var_lower = np.zeros(total_vars, dtype=float)
        var_upper = np.ones(total_vars, dtype=float)
        for active_idx, quarter in enumerate(variable_quarters):
            l_min, l_max = variable_load_bounds[quarter]
            d_lo = (l_min - mean_load) / scale
            d_hi = (l_max - mean_load) / scale
            var_lower[dev_var_offset + active_idx] = d_lo
            var_upper[dev_var_offset + active_idx] = d_hi
            var_lower[sq_var_offset + active_idx] = 0.0
            var_upper[sq_var_offset + active_idx] = np.inf

        # 6. Initial piecewise-linear tangent lower envelope for z_q >= d_q^2:
        #    2 * u * d_q - z_q <= u^2
        def add_tangent_cut(active_idx: int, u: float):
            nonlocal next_row
            row_indices.append(next_row)
            column_indices.append(dev_var_offset + active_idx)
            coefficients.append(2.0 * u)
            row_indices.append(next_row)
            column_indices.append(sq_var_offset + active_idx)
            coefficients.append(-1.0)
            lower_bounds.append(-np.inf)
            upper_bounds.append(u * u)
            next_row += 1

        initial_tangent_count = 9
        for active_idx in range(num_active):
            d_lo = var_lower[dev_var_offset + active_idx]
            d_hi = var_upper[dev_var_offset + active_idx]
            tangent_points = list(np.linspace(d_lo, d_hi, initial_tangent_count))
            if d_lo < 0.0 < d_hi:
                tangent_points.append(0.0)
            for u in tangent_points:
                add_tangent_cut(active_idx, float(u))

        def build_constraints(extra_sum_upper: float | None = None) -> LinearConstraint:
            r = row_indices
            c = column_indices
            v = coefficients
            lb = lower_bounds
            ub = upper_bounds
            rows = next_row
            if extra_sum_upper is not None:
                r = list(row_indices)
                c = list(column_indices)
                v = list(coefficients)
                lb = list(lower_bounds)
                ub = list(upper_bounds)
                for active_idx in range(num_active):
                    r.append(rows)
                    c.append(sq_var_offset + active_idx)
                    v.append(1.0)
                lb.append(-np.inf)
                ub.append(extra_sum_upper)
                rows += 1
            return LinearConstraint(
                coo_matrix((v, (r, c)), shape=(rows, total_vars)).tocsr(),
                np.asarray(lb, dtype=float),
                np.asarray(ub, dtype=float),
            )

        def exact_deviation_and_d(sol_x: np.ndarray) -> tuple[float, np.ndarray]:
            d_vals = sol_x[dev_var_offset : dev_var_offset + num_active]
            return float(np.dot(d_vals, d_vals)), d_vals

        # Stage 2: Exact outer-approximation minimization of sum(d_q^2).
        dev_objective = np.zeros(total_vars, dtype=float)
        dev_objective[sq_var_offset:] = 1.0
        bounds = Bounds(var_lower, var_upper)
        milp_options = {"mip_rel_gap": 1e-9}

        best_exact_dev = np.inf
        best_x = None
        max_oa_iterations = 50
        for _ in range(max_oa_iterations):
            dev_result = milp(
                dev_objective,
                integrality=integrality,
                bounds=bounds,
                constraints=build_constraints(),
                options=milp_options,
            )
            if not dev_result.success:
                raise RuntimeError(
                    f"Schedule average-power optimization failed: {dev_result.message}"
                )

            exact_dev, d_vals = exact_deviation_and_d(dev_result.x)
            z_vals = dev_result.x[sq_var_offset:]
            approx_dev = float(np.sum(z_vals))
            if exact_dev < best_exact_dev:
                best_exact_dev = exact_dev
                best_x = dev_result.x.copy()

            gap_tol = max(1e-7, abs(best_exact_dev) * 1e-8)
            if best_exact_dev - approx_dev <= gap_tol:
                break

            added_cut = False
            for active_idx in range(num_active):
                u = float(d_vals[active_idx])
                if u * u - float(z_vals[active_idx]) > 1e-9:
                    add_tangent_cut(active_idx, u)
                    added_cut = True
            if not added_cut:
                break

        # Stage 3: Minimize schedule movement among optimal-peak, optimal-deviation schedules.
        bound_tol = max(1e-7, abs(best_exact_dev) * 1e-8)
        accept_tol = max(1e-6, abs(best_exact_dev) * 1e-7)
        allowed_dev = best_exact_dev + bound_tol

        move_objective = np.zeros(total_vars, dtype=float)
        move_objective[:variable_count] = movement_cost

        for _ in range(max_oa_iterations):
            tie_break_result = milp(
                move_objective,
                integrality=integrality,
                bounds=bounds,
                constraints=build_constraints(extra_sum_upper=allowed_dev),
                options=milp_options,
            )
            if not tie_break_result.success:
                raise RuntimeError(
                    f"Schedule movement minimization failed: {tie_break_result.message}"
                )

            exact_dev, d_vals = exact_deviation_and_d(tie_break_result.x)
            if exact_dev <= best_exact_dev + accept_tol:
                return tie_break_result.x

            z_vals = tie_break_result.x[sq_var_offset:]
            added_cut = False
            for active_idx in range(num_active):
                u = float(d_vals[active_idx])
                if u * u - float(z_vals[active_idx]) > 1e-9:
                    add_tangent_cut(active_idx, u)
                    added_cut = True
            if not added_cut:
                return tie_break_result.x

        return best_x if best_x is not None else tie_break_result.x

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
