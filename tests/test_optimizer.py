"""
Tests for the optimizer: battery limits, solar availability, energy balance,
end-of-day neutrality, and directive enforcement (K-O, P, Q).
"""

from backend.guardrails import Directive
from backend.models import ScenarioRequest
from backend.optimizer import build_effective_constraints, optimize
from backend.validator import validate_plan

from conftest import make_scenario


def _solve(scenario_dict, directives):
    scenario = ScenarioRequest.model_validate(scenario_dict)
    constraints = build_effective_constraints(scenario, directives)
    plan = optimize(scenario, constraints)
    validate_plan(scenario, constraints, directives, plan)
    return scenario, constraints, plan


def _no_op(idx=0):
    return Directive(note_index=idx, applies=False, directive_type="no_op")


# --- Baseline feasibility ---------------------------------------------------
def test_baseline_plan_is_valid_and_24h():
    scenario, constraints, plan = _solve(make_scenario(), [_no_op()])
    assert len(plan) == 24
    assert [p.hour for p in plan] == list(range(24))


def test_end_of_day_neutrality():
    scenario, constraints, plan = _solve(make_scenario(), [_no_op()])
    assert abs(
        plan[23].battery_energy_after_kwh
        - scenario.battery.initial_energy_kwh
    ) <= 1e-4


def test_energy_balance_every_hour():
    scenario, _, plan = _solve(make_scenario(), [_no_op()])
    for h, p in enumerate(plan):
        discharge = p.battery_kwh if p.battery_action == "discharge" else 0.0
        charge = p.battery_kwh if p.battery_action == "charge" else 0.0
        lhs = p.grid_kwh + p.solar_used_kwh + discharge
        rhs = scenario.hours[h].demand_kwh + charge
        assert abs(lhs - rhs) <= 1e-3


# --- no_charge_window -------------------------------------------------------
def test_no_charge_window_enforced():
    d = Directive(
        note_index=0, applies=True, directive_type="no_charge_window",
        hours=[14, 15],
    )
    scenario, _, plan = _solve(make_scenario(), [d])
    for h in (14, 15):
        assert plan[h].battery_action != "charge"


# --- no_discharge_window ----------------------------------------------------
def test_no_discharge_window_enforced():
    d = Directive(
        note_index=0, applies=True, directive_type="no_discharge_window",
        hours=[18, 19],
    )
    _, _, plan = _solve(make_scenario(), [d])
    for h in (18, 19):
        assert plan[h].battery_action != "discharge"


# --- minimum_battery_reserve ------------------------------------------------
def test_minimum_battery_reserve_enforced():
    d = Directive(
        note_index=0, applies=True, directive_type="minimum_battery_reserve",
        hours=[18, 19, 20], minimum_energy_kwh=150.0,
    )
    _, _, plan = _solve(make_scenario(), [d])
    for h in (18, 19, 20):
        assert plan[h].battery_energy_after_kwh >= 150.0 - 1e-4


# --- max_grid_window --------------------------------------------------------
def test_max_grid_window_enforced():
    d = Directive(
        note_index=0, applies=True, directive_type="max_grid_window",
        hours=[18, 19, 20], max_grid_kwh=120.0,
    )
    _, _, plan = _solve(make_scenario(), [d])
    for h in (18, 19, 20):
        assert plan[h].grid_kwh <= 120.0 + 1e-4


# --- solar_reduction --------------------------------------------------------
def test_solar_reduction_limits_effective_solar():
    d = Directive(
        note_index=0, applies=True, directive_type="solar_reduction",
        hours=[13, 14], factor=0.2,
    )
    scenario, constraints, plan = _solve(make_scenario(), [d])
    for h in (13, 14):
        expected = scenario.hours[h].solar_kwh * 0.2
        assert abs(constraints.effective_solar[h] - expected) <= 1e-6
        assert plan[h].solar_used_kwh <= expected + 1e-4


# --- Charge / discharge rate limits ----------------------------------------
def test_charge_rate_limit_respected():
    _, _, plan = _solve(make_scenario(), [_no_op()])
    for p in plan:
        if p.battery_action == "charge":
            assert p.battery_kwh <= 100.0 + 1e-4


def test_discharge_rate_limit_respected():
    _, _, plan = _solve(make_scenario(), [_no_op()])
    for p in plan:
        if p.battery_action == "discharge":
            assert p.battery_kwh <= 100.0 + 1e-4


# --- Battery minimum / capacity --------------------------------------------
def test_battery_minimum_never_violated():
    scenario, _, plan = _solve(make_scenario(), [_no_op()])
    for p in plan:
        assert p.battery_energy_after_kwh >= scenario.battery.minimum_energy_kwh - 1e-4


def test_battery_capacity_never_exceeded():
    scenario, _, plan = _solve(make_scenario(), [_no_op()])
    for p in plan:
        assert p.battery_energy_after_kwh <= scenario.battery.capacity_kwh + 1e-4


# --- Solar availability -----------------------------------------------------
def test_solar_usage_never_exceeds_available():
    scenario, constraints, plan = _solve(make_scenario(), [_no_op()])
    for h, p in enumerate(plan):
        assert p.solar_used_kwh <= constraints.effective_solar[h] + 1e-4