"""
Shared pytest fixtures and helpers for the GridWise test suite.

We force the offline development fallback so tests do not require an API key.
The offline fallback exercises the same pipeline (interpretation -> guardrails
-> optimizer -> validation) that the real LLM path does.
"""

from __future__ import annotations

import os

# Ensure no real provider is used and the fallback is enabled BEFORE the
# backend package is imported anywhere.
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("ALLOW_LLM_FALLBACK", "true")
os.environ.pop("LLM_API_KEY", None)

import sys
from pathlib import Path

# Make the project root importable as a package root.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_scenario(
    notes=None,
    scenario_id="TEST-1",
    demand=180.0,
    solar_pattern=None,
    tariff=7.0,
    battery=None,
):
    """Build a valid ScenarioRequest dict with sensible defaults."""
    if notes is None:
        notes = ["No operational changes today."]

    if solar_pattern is None:
        # A simple bell curve peaking around midday.
        solar_pattern = [
            0, 0, 0, 0, 0, 0,
            10, 40, 90, 150, 200, 230,
            250, 240, 210, 160, 100, 50,
            15, 0, 0, 0, 0, 0,
        ]

    hours = []
    for h in range(24):
        hours.append(
            {
                "hour": h,
                "demand_kwh": demand,
                "solar_kwh": float(solar_pattern[h]),
                "tariff_bdt_per_kwh": tariff,
            }
        )

    if battery is None:
        battery = {
            "capacity_kwh": 500,
            "initial_energy_kwh": 200,
            "minimum_energy_kwh": 50,
            "max_charge_kwh_per_hour": 100,
            "max_discharge_kwh_per_hour": 100,
        }

    return {
        "scenario_id": scenario_id,
        "operator_notes": notes,
        "hours": hours,
        "battery": battery,
    }