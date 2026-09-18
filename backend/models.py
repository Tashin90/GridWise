"""
Pydantic models for the GridWise API.

These models define the exact request schema the judge sends and the exact
response schema we must return.  They also define the structured directive
objects produced by the LLM interpretation layer.

The request models are exposed directly as the FastAPI request body, which is
why Swagger UI / OpenAPI shows a full "Request body" section for
POST /optimize-energy.
"""

from __future__ import annotations

import math
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Supported directive types
# ---------------------------------------------------------------------------
DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

SUPPORTED_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class HourRecord(BaseModel):
    """One hourly energy record (24 of these per request)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "hour": 12,
                "demand_kwh": 180.0,
                "solar_kwh": 250.0,
                "tariff_bdt_per_kwh": 7.0,
            }
        }
    )

    hour: int = Field(..., ge=0, le=23, description="Hour of day, 0..23")
    demand_kwh: float = Field(..., description="Energy demand in kWh")
    solar_kwh: float = Field(..., description="Available solar energy in kWh")
    tariff_bdt_per_kwh: float = Field(..., description="Grid tariff in BDT/kWh")

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def _finite_non_negative(cls, v: float) -> float:
        if v is None or not math.isfinite(v):
            raise ValueError("value must be a finite number")
        if v < 0:
            raise ValueError("value must be non-negative")
        return v


class BatteryConfig(BaseModel):
    """Battery configuration for the scenario."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "capacity_kwh": 500,
                "initial_energy_kwh": 200,
                "minimum_energy_kwh": 50,
                "max_charge_kwh_per_hour": 100,
                "max_discharge_kwh_per_hour": 100,
            }
        }
    )

    capacity_kwh: float = Field(..., gt=0, description="Total battery capacity")
    initial_energy_kwh: float = Field(..., description="Energy at hour 0")
    minimum_energy_kwh: float = Field(..., description="Minimum allowed energy")
    max_charge_kwh_per_hour: float = Field(..., description="Max charge per hour")
    max_discharge_kwh_per_hour: float = Field(..., description="Max discharge/hour")

    @field_validator(
        "capacity_kwh",
        "initial_energy_kwh",
        "minimum_energy_kwh",
        "max_charge_kwh_per_hour",
        "max_discharge_kwh_per_hour",
    )
    @classmethod
    def _finite_non_negative(cls, v: float) -> float:
        if v is None or not math.isfinite(v):
            raise ValueError("value must be a finite number")
        if v < 0:
            raise ValueError("value must be non-negative")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "BatteryConfig":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError(
                "initial_energy_kwh cannot be below minimum_energy_kwh"
            )
        return self


# A complete, valid 24-hour example used for the OpenAPI request body.
_EXAMPLE_SOLAR = [
    0, 0, 0, 0, 0, 0, 10, 40, 90, 150, 200, 230,
    250, 240, 210, 160, 100, 50, 15, 0, 0, 0, 0, 0,
]
_SCENARIO_EXAMPLE = {
    "scenario_id": "GRID-101",
    "operator_notes": [
        "Battery charging is not allowed from 2 PM to 4 PM.",
        "Expect an 80% reduction in rooftop solar during the 1-3 PM window.",
        "The campus will host a seminar today.",
    ],
    "hours": [
        {
            "hour": h,
            "demand_kwh": 180.0,
            "solar_kwh": float(_EXAMPLE_SOLAR[h]),
            "tariff_bdt_per_kwh": 7.0,
        }
        for h in range(24)
    ],
    "battery": {
        "capacity_kwh": 500,
        "initial_energy_kwh": 200,
        "minimum_energy_kwh": 50,
        "max_charge_kwh_per_hour": 100,
        "max_discharge_kwh_per_hour": 100,
    },
}


class ScenarioRequest(BaseModel):
    """The full scenario object accepted by POST /optimize-energy."""

    model_config = ConfigDict(json_schema_extra={"example": _SCENARIO_EXAMPLE})

    scenario_id: str = Field(..., description="Scenario identifier")
    operator_notes: List[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1 to 3 natural-language operator notes",
    )
    hours: List[HourRecord] = Field(
        ...,
        min_length=24,
        max_length=24,
        description="Exactly 24 hourly records (hours 0..23)",
    )
    battery: BatteryConfig = Field(..., description="Battery configuration")

    @field_validator("scenario_id")
    @classmethod
    def _scenario_id_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or v.strip() == "":
            raise ValueError("scenario_id must be a non-empty string")
        return v

    @field_validator("operator_notes")
    @classmethod
    def _notes_valid(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("operator_notes must be a list")
        if not (1 <= len(v) <= 3):
            raise ValueError("operator_notes must contain 1 to 3 notes")
        for note in v:
            if not isinstance(note, str) or note.strip() == "":
                raise ValueError("each operator note must be a non-empty string")
        return v

    @field_validator("hours")
    @classmethod
    def _hours_valid(cls, v: List[HourRecord]) -> List[HourRecord]:
        if len(v) != 24:
            raise ValueError("hours must contain exactly 24 entries")
        hour_numbers = [h.hour for h in v]
        if sorted(hour_numbers) != list(range(24)):
            raise ValueError("hours must be exactly 0 through 23, unique")
        if hour_numbers != sorted(hour_numbers):
            raise ValueError("hours must be in ascending order")
        return v


# ---------------------------------------------------------------------------
# Directive interpretation models
# ---------------------------------------------------------------------------
class DirectiveInterpretation(BaseModel):
    """
    One interpretation entry produced for one operator note.

    This is the machine-checkable interpretation the judge validates.
    """

    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Optional[dict[str, Any]] = None
    explanation: str = ""


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class HourlyPlanItem(BaseModel):
    """One hour of the final optimized schedule."""

    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    """The full response returned by POST /optimize-energy."""

    scenario_id: str
    directive_interpretation: List[DirectiveInterpretation]
    hourly_plan: List[HourlyPlanItem]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str