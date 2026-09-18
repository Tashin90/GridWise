"""
Tests for deterministic guardrails (R, S, T and related).

The guardrails treat LLM output as untrusted and must reject malformed,
duplicated, missing, or unsupported interpretations without crashing.
"""

import pytest

from backend.guardrails import (
    GuardrailError,
    validated_directives_to_interpretations,
)
from backend.models import BatteryConfig

BATTERY = BatteryConfig(
    capacity_kwh=500,
    initial_energy_kwh=200,
    minimum_energy_kwh=50,
    max_charge_kwh_per_hour=100,
    max_discharge_kwh_per_hour=100,
)

NOTES = ["note a", "note b", "note c"]


def _valid_entry(idx, dtype="no_op", applies=False, structured=None):
    return {
        "note_index": idx,
        "applies": applies,
        "directive_type": dtype,
        "structured_adjustment": structured,
        "explanation": "",
    }


def test_valid_no_op_list():
    raw = [_valid_entry(0), _valid_entry(1), _valid_entry(2)]
    result = validated_directives_to_interpretations(raw, NOTES, BATTERY)
    assert len(result) == 3
    assert all(d.directive_type == "no_op" for d in result)


def test_missing_note_index_rejected():
    raw = [_valid_entry(0), _valid_entry(2)]  # missing 1
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_duplicate_note_index_rejected():
    raw = [_valid_entry(0), _valid_entry(0), _valid_entry(2)]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_out_of_range_note_index_rejected():
    raw = [_valid_entry(0), _valid_entry(1), _valid_entry(5)]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_unsupported_directive_type_rejected():
    raw = [
        _valid_entry(0, dtype="turn_off_everything", applies=True, structured={}),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_no_op_must_have_applies_false():
    raw = [_valid_entry(0, dtype="no_op", applies=True), _valid_entry(1), _valid_entry(2)]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_no_op_must_have_null_structured():
    raw = [
        _valid_entry(0, dtype="no_op", applies=False, structured={"hours": [1]}),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_non_no_op_must_have_applies_true():
    raw = [
        _valid_entry(0, dtype="no_charge_window", applies=False, structured={"hours": [1]}),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_solar_factor_out_of_range_rejected():
    raw = [
        _valid_entry(
            0,
            dtype="solar_reduction",
            applies=True,
            structured={"hours": [13], "factor": 1.5},
        ),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_hours_out_of_range_rejected():
    raw = [
        _valid_entry(
            0,
            dtype="no_charge_window",
            applies=True,
            structured={"hours": [25]},
        ),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_hours_not_ascending_rejected():
    raw = [
        _valid_entry(
            0,
            dtype="no_charge_window",
            applies=True,
            structured={"hours": [15, 14]},
        ),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_reserve_exceeding_capacity_rejected():
    raw = [
        _valid_entry(
            0,
            dtype="minimum_battery_reserve",
            applies=True,
            structured={"hours": [18], "minimum_energy_kwh": 9999},
        ),
        _valid_entry(1),
        _valid_entry(2),
    ]
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations(raw, NOTES, BATTERY)


def test_non_list_output_rejected():
    with pytest.raises(GuardrailError):
        validated_directives_to_interpretations({"oops": True}, NOTES, BATTERY)


def test_valid_directive_roundtrip():
    raw = [
        _valid_entry(
            0,
            dtype="solar_reduction",
            applies=True,
            structured={"hours": [13, 14], "factor": 0.2},
        ),
        _valid_entry(1),
        _valid_entry(2),
    ]
    result = validated_directives_to_interpretations(raw, NOTES, BATTERY)
    interp = result[0].to_interpretation()
    assert interp.directive_type == "solar_reduction"
    assert interp.structured_adjustment == {"hours": [13, 14], "factor": 0.2}