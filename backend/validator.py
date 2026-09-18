"""
Independent replay validation of the generated schedule.

We do NOT trust the optimizer's reported totals.  This module replays the
hourly plan from scratch, recomputes every total, and verifies every energy,
battery, and operator-directive constraint.  If anything is wrong it raises
`ValidationError`, which the API maps to a controlled error response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .guardrails import Directive
from .models import HourlyPlanItem, ScenarioRequest
from .optimizer import EffectiveConstraints

# Tolerance for floating-point comparisons (judge uses ~0.01).
TOL = 1e-4


class ValidationError(Exception):
    """Raised when the generated plan fails independent replay validation."""


@dataclass
class Totals:
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


@dataclass
class ValidationReport:
    totals: Totals


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_plan(
    scenario: ScenarioRequest,
    constraints: EffectiveConstraints,
    directives: List[Directive],
    plan: List[HourlyPlanItem],
) -> ValidationReport:
    """Replay the plan and verify every constraint. Returns recomputed totals."""
    battery = scenario.battery
    hours = scenario.hours

    # 1) Exactly 24 hourly entries.
    _check(len(plan) == 24, f"plan must have 24 entries, got {len(plan)}")

    # 2) Hours are exactly 0..23, unique, ascending.
    plan_hours = [p.hour for p in plan]
    _check(plan_hours == list(range(24)), "plan hours must be exactly 0..23 in order")

    # 3) All numeric values finite and non-negative.
    for p in plan:
        for name, value in (
            ("grid_kwh", p.grid_kwh),
            ("solar_used_kwh", p.solar_used_kwh),
            ("battery_kwh", p.battery_kwh),
            ("battery_energy_after_kwh", p.battery_energy_after_kwh),
        ):
            _check(
                value == value and abs(value) != float("inf"),
                f"hour {p.hour}: {name} must be finite",
            )
            _check(value >= -TOL, f"hour {p.hour}: {name} must be non-negative")
        _check(
            p.battery_action in ("charge", "discharge", "idle"),
            f"hour {p.hour}: invalid battery_action {p.battery_action!r}",
        )
        if p.battery_action == "idle":
            _check(
                abs(p.battery_kwh) <= TOL,
                f"hour {p.hour}: idle action must have battery_kwh == 0",
            )

    # 4) Replay battery dynamics and energy balance hour by hour.
    e_before = battery.initial_energy_kwh
    for h, p in enumerate(plan):
        demand = hours[h].demand_kwh
        eff_solar = constraints.effective_solar[h]

        # Solar availability.
        _check(
            p.solar_used_kwh <= eff_solar + TOL,
            f"hour {h}: solar_used {p.solar_used_kwh} exceeds effective solar {eff_solar}",
        )

        # Determine charge/discharge from the action.
        if p.battery_action == "charge":
            charge = p.battery_kwh
            discharge = 0.0
        elif p.battery_action == "discharge":
            charge = 0.0
            discharge = p.battery_kwh
        else:
            charge = 0.0
            discharge = 0.0

        # Hourly charge/discharge limits.
        _check(
            charge <= battery.max_charge_kwh_per_hour + TOL,
            f"hour {h}: charge {charge} exceeds max_charge_kwh_per_hour",
        )
        _check(
            discharge <= battery.max_discharge_kwh_per_hour + TOL,
            f"hour {h}: discharge {discharge} exceeds max_discharge_kwh_per_hour",
        )

        # Energy balance: grid + solar + discharge == demand + charge.
        lhs = p.grid_kwh + p.solar_used_kwh + discharge
        rhs = demand + charge
        _check(
            abs(lhs - rhs) <= TOL,
            f"hour {h}: energy balance violated ({lhs} != {rhs})",
        )

        # Battery transition.
        e_after = e_before + charge - discharge
        _check(
            abs(e_after - p.battery_energy_after_kwh) <= TOL,
            f"hour {h}: battery transition mismatch "
            f"(expected {e_after}, got {p.battery_energy_after_kwh})",
        )

        # Battery bounds.
        _check(
            p.battery_energy_after_kwh <= battery.capacity_kwh + TOL,
            f"hour {h}: battery energy exceeds capacity",
        )
        _check(
            p.battery_energy_after_kwh >= battery.minimum_energy_kwh - TOL,
            f"hour {h}: battery energy below minimum",
        )

        e_before = p.battery_energy_after_kwh

    # 5) End-of-day battery neutrality.
    _check(
        abs(plan[23].battery_energy_after_kwh - battery.initial_energy_kwh) <= TOL,
        "final battery energy must equal initial battery energy",
    )

    # 6) Operator directive constraints.
    for d in directives:
        if not d.applies or d.directive_type == "no_op":
            continue
        if d.directive_type == "no_charge_window":
            for h in d.hours:
                _check(
                    plan[h].battery_action != "charge",
                    f"hour {h}: no_charge_window violated",
                )
        elif d.directive_type == "no_discharge_window":
            for h in d.hours:
                _check(
                    plan[h].battery_action != "discharge",
                    f"hour {h}: no_discharge_window violated",
                )
        elif d.directive_type == "minimum_battery_reserve":
            for h in d.hours:
                _check(
                    plan[h].battery_energy_after_kwh >= d.minimum_energy_kwh - TOL,
                    f"hour {h}: minimum_battery_reserve violated",
                )
        elif d.directive_type == "max_grid_window":
            for h in d.hours:
                _check(
                    plan[h].grid_kwh <= d.max_grid_kwh + TOL,
                    f"hour {h}: max_grid_window violated",
                )
        elif d.directive_type == "solar_reduction":
            for h in d.hours:
                original = hours[h].solar_kwh
                expected = original * d.factor
                _check(
                    plan[h].solar_used_kwh <= expected + TOL,
                    f"hour {h}: solar_reduction violated",
                )

    # 7) Recompute totals independently from the hourly plan.
    total_grid = sum(p.grid_kwh for p in plan)
    total_cost = sum(p.grid_kwh * hours[p.hour].tariff_bdt_per_kwh for p in plan)
    peak_grid = max(p.grid_kwh for p in plan)

    return ValidationReport(
        totals=Totals(
            total_grid_kwh=round(total_grid, 6),
            total_cost_bdt=round(total_cost, 6),
            peak_grid_kwh=round(peak_grid, 6),
        )
    )