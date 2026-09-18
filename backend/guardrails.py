"""
Deterministic guardrails for LLM output.

The LLM is treated as an UNTRUSTED component.  Everything it returns is
validated here before it can influence the optimizer.  If the LLM produces
malformed, unsupported, missing, or duplicated interpretations we raise a
`GuardrailError` (mapped to HTTP 422 by the API) rather than crashing or
silently inventing a rule.

Supported directives (and ONLY these):
    solar_reduction          {hours, factor}
    minimum_battery_reserve  {hours, minimum_energy_kwh}
    no_charge_window         {hours}
    no_discharge_window      {hours}
    max_grid_window          {hours, max_grid_kwh}
    no_op                    (structured_adjustment = null)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional

from .models import BatteryConfig, DirectiveInterpretation


class GuardrailError(Exception):
    """Raised when LLM output fails deterministic validation."""


# ---------------------------------------------------------------------------
# Typed directive object
# ---------------------------------------------------------------------------
@dataclass
class Directive:
    """A validated, normalized directive ready to be applied."""

    note_index: int
    applies: bool
    directive_type: str
    hours: List[int] = field(default_factory=list)
    factor: Optional[float] = None
    minimum_energy_kwh: Optional[float] = None
    max_grid_kwh: Optional[float] = None
    explanation: str = ""

    def to_interpretation(self) -> DirectiveInterpretation:
        """Convert back to the machine-checkable interpretation model."""
        if self.directive_type == "no_op":
            structured = None
        elif self.directive_type == "solar_reduction":
            structured = {"hours": self.hours, "factor": self.factor}
        elif self.directive_type == "minimum_battery_reserve":
            structured = {
                "hours": self.hours,
                "minimum_energy_kwh": self.minimum_energy_kwh,
            }
        elif self.directive_type in ("no_charge_window", "no_discharge_window"):
            structured = {"hours": self.hours}
        elif self.directive_type == "max_grid_window":
            structured = {"hours": self.hours, "max_grid_kwh": self.max_grid_kwh}
        else:  # pragma: no cover - guarded earlier
            structured = None

        return DirectiveInterpretation(
            note_index=self.note_index,
            applies=self.applies,
            directive_type=self.directive_type,
            structured_adjustment=structured,
            explanation=self.explanation,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GuardrailError(f"'{name}' must be a number")
    if not math.isfinite(float(value)):
        raise GuardrailError(f"'{name}' must be finite")
    return float(value)


def _validate_hours(hours: Any) -> List[int]:
    if not isinstance(hours, list) or not hours:
        raise GuardrailError("'hours' must be a non-empty list of integers")
    cleaned: List[int] = []
    for h in hours:
        if isinstance(h, bool) or not isinstance(h, int):
            # Accept floats that are whole numbers (some LLMs emit 13.0).
            if isinstance(h, float) and float(h).is_integer():
                h = int(h)
            else:
                raise GuardrailError(f"hour value {h!r} is not an integer")
        if not (0 <= h <= 23):
            raise GuardrailError(f"hour {h} is outside 0..23")
        cleaned.append(h)
    if len(set(cleaned)) != len(cleaned):
        raise GuardrailError("'hours' contains duplicate values")
    if cleaned != sorted(cleaned):
        raise GuardrailError("'hours' must be in ascending order")
    return cleaned


# ---------------------------------------------------------------------------
# Per-directive validators
# ---------------------------------------------------------------------------
def _validate_solar_reduction(directive: dict, battery: BatteryConfig) -> Directive:
    hours = _validate_hours(directive.get("hours"))
    factor = _require_finite_number(directive.get("factor"), "factor")
    if not (0.0 <= factor <= 1.0):
        raise GuardrailError("solar_reduction 'factor' must be between 0 and 1")
    return Directive(
        note_index=-1,
        applies=True,
        directive_type="solar_reduction",
        hours=hours,
        factor=factor,
    )


def _validate_minimum_battery_reserve(
    directive: dict, battery: BatteryConfig
) -> Directive:
    hours = _validate_hours(directive.get("hours"))
    reserve = _require_finite_number(
        directive.get("minimum_energy_kwh"), "minimum_energy_kwh"
    )
    if reserve < 0:
        raise GuardrailError("minimum_energy_kwh must be non-negative")
    if reserve > battery.capacity_kwh + 1e-9:
        raise GuardrailError(
            "minimum_battery_reserve exceeds battery capacity"
        )
    return Directive(
        note_index=-1,
        applies=True,
        directive_type="minimum_battery_reserve",
        hours=hours,
        minimum_energy_kwh=reserve,
    )


def _validate_window_no_value(directive: dict, dtype: str) -> Directive:
    hours = _validate_hours(directive.get("hours"))
    return Directive(
        note_index=-1,
        applies=True,
        directive_type=dtype,
        hours=hours,
    )


def _validate_max_grid_window(directive: dict, battery: BatteryConfig) -> Directive:
    hours = _validate_hours(directive.get("hours"))
    max_grid = _require_finite_number(
        directive.get("max_grid_kwh"), "max_grid_kwh"
    )
    if max_grid < 0:
        raise GuardrailError("max_grid_kwh must be non-negative")
    return Directive(
        note_index=-1,
        applies=True,
        directive_type="max_grid_window",
        hours=hours,
        max_grid_kwh=max_grid,
    )


_VALIDATORS = {
    "solar_reduction": _validate_solar_reduction,
    "minimum_battery_reserve": _validate_minimum_battery_reserve,
    "no_charge_window": lambda d, b: _validate_window_no_value(d, "no_charge_window"),
    "no_discharge_window": lambda d, b: _validate_window_no_value(d, "no_discharge_window"),
    "max_grid_window": _validate_max_grid_window,
}


# ---------------------------------------------------------------------------
# Top-level validation
# ---------------------------------------------------------------------------
def validated_directives_to_interpretations(
    raw: Any,
    operator_notes: List[str],
    battery: BatteryConfig,
) -> List[Directive]:
    """
    Validate the raw LLM output and return normalized Directive objects.

    Enforces:
      * output is a list
      * exactly one entry per note (no missing, no duplicate note_index)
      * entries are in ascending note_index order starting at 0
      * note_index maps to a real note
      * directive_type is supported
      * applies semantics (no_op -> applies=False; others -> applies=True)
      * structured_adjustment is null only for no_op
      * field-level checks per directive type
    """
    if not isinstance(raw, list):
        raise GuardrailError("LLM output must be a list of interpretations")

    expected = list(range(len(operator_notes)))

    # Sort defensively, then verify ordering and completeness.
    seen: dict[int, dict] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise GuardrailError("each interpretation must be a JSON object")
        if "note_index" not in entry:
            raise GuardrailError("interpretation is missing 'note_index'")
        idx = entry.get("note_index")
        if isinstance(idx, bool) or not isinstance(idx, int):
            if isinstance(idx, float) and float(idx).is_integer():
                idx = int(idx)
            else:
                raise GuardrailError("note_index must be an integer")
        if idx in seen:
            raise GuardrailError(f"duplicate note_index {idx}")
        if idx not in expected:
            raise GuardrailError(f"note_index {idx} does not map to a note")
        seen[idx] = entry

    if sorted(seen.keys()) != expected:
        raise GuardrailError(
            f"expected note_index values {expected}, got {sorted(seen.keys())}"
        )
    # Preserve required ascending order.
    ordered = [seen[i] for i in expected]

    directives: List[Directive] = []
    for idx, entry in zip(expected, ordered):
        dtype = entry.get("directive_type")
        if dtype not in _VALIDATORS and dtype != "no_op":
            raise GuardrailError(f"unsupported directive_type {dtype!r}")

        applies = entry.get("applies")
        if not isinstance(applies, bool):
            raise GuardrailError("'applies' must be a boolean")

        structured = entry.get("structured_adjustment")
        explanation = str(entry.get("explanation", "") or "")

        if dtype == "no_op":
            if applies is not False:
                raise GuardrailError("no_op must have applies=false")
            if structured is not None:
                raise GuardrailError("no_op must have structured_adjustment=null")
            directives.append(
                Directive(
                    note_index=idx,
                    applies=False,
                    directive_type="no_op",
                    explanation=explanation or "This note does not affect the schedule.",
                )
            )
            continue

        # Non-no_op directives must apply and carry a structured adjustment.
        if applies is not True:
            raise GuardrailError(
                f"{dtype} must have applies=true (applies=false is only for no_op)"
            )
        if not isinstance(structured, dict):
            raise GuardrailError(
                f"{dtype} requires a structured_adjustment object"
            )

        validator = _VALIDATORS[dtype]
        try:
            directive = validator(structured, battery)
        except GuardrailError:
            raise
        except Exception as exc:  # defensive: never crash on odd LLM output
            raise GuardrailError(f"invalid {dtype} adjustment: {exc}") from exc

        directive.note_index = idx
        directive.explanation = explanation
        directives.append(directive)

    return directives