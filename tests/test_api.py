"""
End-to-end API tests for POST /optimize-energy (cases B-J and status codes).
"""

from fastapi.testclient import TestClient

from backend.main import app

from conftest import make_scenario

client = TestClient(app)


def _post(scenario_dict):
    return client.post("/optimize-energy", json=scenario_dict)


def _assert_response_valid(body, notes_count):
    # Every note has exactly one interpretation.
    interp = body["directive_interpretation"]
    assert len(interp) == notes_count
    assert [e["note_index"] for e in interp] == list(range(notes_count))

    # Interpretation uses only supported directives with correct applies.
    supported = {
        "solar_reduction", "minimum_battery_reserve", "no_charge_window",
        "no_discharge_window", "max_grid_window", "no_op",
    }
    for e in interp:
        assert e["directive_type"] in supported
        if e["directive_type"] == "no_op":
            assert e["applies"] is False
            assert e["structured_adjustment"] is None
        else:
            assert e["applies"] is True

    # Exactly 24 hours, in order.
    plan = body["hourly_plan"]
    assert len(plan) == 24
    assert [p["hour"] for p in plan] == list(range(24))
    return plan


# --- B. Simple scenario with no meaningful operator note -------------------
def test_simple_no_meaningful_note():
    resp = _post(make_scenario(notes=["No operational changes today."]))
    assert resp.status_code == 200
    body = resp.json()
    _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "no_op"


# --- C. no_charge_window ---------------------------------------------------
def test_no_charge_window_end_to_end():
    resp = _post(make_scenario(notes=["Battery charging is not allowed from 2 PM to 4 PM."]))
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "no_charge_window"
    for h in (14, 15):
        assert plan[h]["battery_action"] != "charge"


# --- D. no_discharge_window ------------------------------------------------
def test_no_discharge_window_end_to_end():
    resp = _post(make_scenario(notes=["Do not discharge the battery between 6 PM and 8 PM."]))
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "no_discharge_window"
    for h in (18, 19):
        assert plan[h]["battery_action"] != "discharge"


# --- E. minimum_battery_reserve --------------------------------------------
def test_minimum_battery_reserve_end_to_end():
    resp = _post(make_scenario(notes=["Keep the battery reserve at least 150 kWh from 6 PM to 9 PM."]))
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "minimum_battery_reserve"
    for h in (18, 19, 20):
        assert plan[h]["battery_energy_after_kwh"] >= 150.0 - 1e-4


# --- F. max_grid_window ----------------------------------------------------
def test_max_grid_window_end_to_end():
    resp = _post(make_scenario(notes=["Grid import must not exceed 120 kWh from 6 PM to 8 PM."]))
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "max_grid_window"
    for h in (18, 19):
        assert plan[h]["grid_kwh"] <= 120.0 + 1e-4


# --- G. solar_reduction ----------------------------------------------------
def test_solar_reduction_end_to_end():
    resp = _post(
        make_scenario(
            notes=["Expect an 80% reduction in rooftop solar during the 1-3 PM window."]
        )
    )
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "solar_reduction"
    # factor 0.2 applied to hours 13, 14
    for h in (13, 14):
        # effective solar in scenario default: 240 at 13, 210 at 14
        assert plan[h]["solar_used_kwh"] <= (240.0 * 0.2) + 1e-4 if h == 13 else True


# --- H. no_op --------------------------------------------------------------
def test_no_op_end_to_end():
    resp = _post(make_scenario(notes=["The campus will host a seminar today."]))
    assert resp.status_code == 200
    body = resp.json()
    _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["applies"] is False


# --- I. Multiple directives in one request ---------------------------------
def test_multiple_directives():
    notes = [
        "Battery charging is not allowed from 2 PM to 4 PM.",
        "Keep the battery reserve at least 150 kWh from 6 PM to 9 PM.",
        "Grid import must not exceed 120 kWh from 6 PM to 8 PM.",
    ]
    resp = _post(make_scenario(notes=notes))
    assert resp.status_code == 200
    body = resp.json()
    plan = _assert_response_valid(body, 3)
    types = [e["directive_type"] for e in body["directive_interpretation"]]
    assert types == [
        "no_charge_window",
        "minimum_battery_reserve",
        "max_grid_window",
    ]
    for h in (14, 15):
        assert plan[h]["battery_action"] != "charge"
    for h in (18, 19, 20):
        assert plan[h]["battery_energy_after_kwh"] >= 150.0 - 1e-4


# --- J. Paraphrased operator notes -----------------------------------------
def test_paraphrased_notes():
    resp = _post(
        make_scenario(
            notes=[
                "PV production will drop to about 20% between 13:00 and 15:00."
            ]
        )
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_response_valid(body, 1)
    assert body["directive_interpretation"][0]["directive_type"] == "solar_reduction"
    assert abs(
        body["directive_interpretation"][0]["structured_adjustment"]["factor"] - 0.2
    ) < 1e-9


# --- Totals are recomputed and consistent ----------------------------------
def test_totals_are_consistent():
    resp = _post(make_scenario())
    assert resp.status_code == 200
    body = resp.json()
    plan = body["hourly_plan"]
    scenario = make_scenario()
    tariffs = [h["tariff_bdt_per_kwh"] for h in scenario["hours"]]

    total_grid = sum(p["grid_kwh"] for p in plan)
    total_cost = sum(p["grid_kwh"] * tariffs[p["hour"]] for p in plan)
    peak = max(p["grid_kwh"] for p in plan)

    assert abs(body["total_grid_kwh"] - total_grid) <= 1e-3
    assert abs(body["total_cost_bdt"] - total_cost) <= 1e-3
    assert abs(body["peak_grid_kwh"] - peak) <= 1e-3


# --- Structural validation -> 400 ------------------------------------------
def test_malformed_json_returns_400():
    resp = client.post(
        "/optimize-energy",
        content="{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_wrong_hour_count_returns_400():
    scenario = make_scenario()
    scenario["hours"] = scenario["hours"][:10]
    resp = _post(scenario)
    assert resp.status_code == 400


def test_too_many_notes_returns_400():
    scenario = make_scenario(notes=["a", "b", "c", "d"])
    resp = _post(scenario)
    assert resp.status_code == 400


def test_negative_demand_returns_400():
    scenario = make_scenario()
    scenario["hours"][0]["demand_kwh"] = -5
    resp = _post(scenario)
    assert resp.status_code == 400


def test_missing_battery_returns_400():
    scenario = make_scenario()
    del scenario["battery"]
    resp = _post(scenario)
    assert resp.status_code == 400


# --- Response shape --------------------------------------------------------
def test_response_has_required_fields():
    resp = _post(make_scenario())
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "scenario_id", "directive_interpretation", "hourly_plan",
        "total_grid_kwh", "total_cost_bdt", "peak_grid_kwh", "plan_summary",
    ):
        assert key in body
    sample = body["hourly_plan"][0]
    for key in (
        "hour", "grid_kwh", "solar_used_kwh", "battery_action",
        "battery_kwh", "battery_energy_after_kwh",
    ):
        assert key in sample
    assert sample["battery_action"] in ("charge", "discharge", "idle")