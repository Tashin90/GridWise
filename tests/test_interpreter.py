"""
Tests for the LLM interpretation layer (offline fallback provider).

These verify paraphrase robustness and time-range handling. The offline
fallback is a heuristic stand-in for a real LLM; the same pipeline and
guardrails apply to both.
"""

from backend.llm_interpreter import OfflineFallbackProvider, _extract_hours


provider = OfflineFallbackProvider()


def _one(note):
    return provider.interpret([note])[0]


# --- Time range parsing -----------------------------------------------------
def test_range_1pm_to_3pm_is_13_14():
    assert _extract_hours("from 1 pm to 3 pm") == [13, 14]


def test_range_2pm_to_4pm_is_14_15():
    assert _extract_hours("2 pm to 4 pm") == [14, 15]


def test_range_24h_clock():
    assert _extract_hours("13:00 to 15:00") == [13, 14]


def test_explicit_hour_list():
    assert _extract_hours("hours 18, 19, 20") == [18, 19, 20]


# --- solar_reduction paraphrases -------------------------------------------
def test_solar_reduction_drop_to_20_percent():
    r = _one("PV production will drop to about 20% between 13:00 and 15:00.")
    assert r["directive_type"] == "solar_reduction"
    assert r["structured_adjustment"]["hours"] == [13, 14]
    assert abs(r["structured_adjustment"]["factor"] - 0.2) < 1e-9


def test_solar_reduction_one_fifth():
    r = _one(
        "Panel washing from one until three will leave roughly one-fifth of "
        "normal solar output."
    )
    assert r["directive_type"] == "solar_reduction"
    assert abs(r["structured_adjustment"]["factor"] - 0.2) < 1e-9


def test_solar_reduction_80_percent_reduction():
    r = _one(
        "Expect an 80% reduction in rooftop solar during the 1-3 PM "
        "maintenance window."
    )
    assert r["directive_type"] == "solar_reduction"
    assert r["structured_adjustment"]["hours"] == [13, 14]
    assert abs(r["structured_adjustment"]["factor"] - 0.2) < 1e-9


# --- other directives -------------------------------------------------------
def test_no_charge_window():
    r = _one("Battery charging is not allowed from 2 PM to 4 PM.")
    assert r["directive_type"] == "no_charge_window"
    assert r["structured_adjustment"]["hours"] == [14, 15]


def test_no_discharge_window():
    r = _one("Do not discharge the battery between 6 PM and 8 PM.")
    assert r["directive_type"] == "no_discharge_window"
    assert r["structured_adjustment"]["hours"] == [18, 19]


def test_minimum_battery_reserve():
    r = _one("Keep the battery reserve at least 120 kWh from 6 PM to 9 PM.")
    assert r["directive_type"] == "minimum_battery_reserve"
    assert r["structured_adjustment"]["minimum_energy_kwh"] == 120.0


def test_max_grid_window():
    r = _one("Grid import must not exceed 100 kWh from 6 PM to 8 PM.")
    assert r["directive_type"] == "max_grid_window"
    assert r["structured_adjustment"]["max_grid_kwh"] == 100.0


def test_no_op_for_irrelevant_note():
    r = _one("The campus cafeteria will serve pasta today.")
    assert r["directive_type"] == "no_op"
    assert r["applies"] is False
    assert r["structured_adjustment"] is None


def test_one_entry_per_note_in_order():
    notes = [
        "Battery charging is not allowed from 2 PM to 4 PM.",
        "The library will be closed.",
        "Grid import must not exceed 100 kWh from 6 PM to 8 PM.",
    ]
    results = provider.interpret(notes)
    assert [r["note_index"] for r in results] == [0, 1, 2]