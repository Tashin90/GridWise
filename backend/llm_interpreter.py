"""
LLM interpretation layer.

This module is the ONLY place where operator notes are turned into structured
directives.  The LLM is a first-class part of the interpretation path — it is
NOT used merely for cosmetic summary text.

Provider abstraction
--------------------
`interpret_notes(notes)` selects a provider based on `config.settings`:

    LLM_PROVIDER=openai  -> OpenAI-compatible chat completions API
    LLM_PROVIDER=gemini  -> Google Gemini generateContent API
    LLM_PROVIDER=none    -> no real provider configured

When no real provider/key is configured, a clearly-marked OFFLINE DEV FALLBACK
is used *only if* ALLOW_LLM_FALLBACK is true.  The fallback is a deterministic
heuristic parser intended for local testing; it is explicitly NOT a real LLM
and must not be used in judge/production mode.  Set ALLOW_LLM_FALLBACK=false
to make the service fail loudly instead of silently falling back.

The provider returns a list of raw interpretation dicts (untrusted).  All
validation happens in guardrails.py.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, List, Optional

from .config import settings

logger = logging.getLogger("gridwise.llm")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the operator-directive interpreter for a smart-campus
energy optimization system. You convert natural-language operator notes into
structured directives for a 24-hour (hours 0..23) energy schedule.

You MUST return a JSON object with a single key "interpretations" whose value
is a list with EXACTLY ONE entry per operator note, in note_index order
starting at 0. Never skip, merge, or duplicate notes.

Each entry has this shape:
{
  "note_index": <int>,
  "applies": <bool>,
  "directive_type": <one of the supported types>,
  "structured_adjustment": <object or null>,
  "explanation": "<short reason>"
}

SUPPORTED DIRECTIVE TYPES (use ONLY these):
1. "solar_reduction"         -> {"hours": [..], "factor": <0..1>}
   Reduce usable solar. factor is the FRACTION of normal solar that remains.
   "80% reduction" => factor 0.2. "drop to 20%" => factor 0.2.
2. "minimum_battery_reserve" -> {"hours": [..], "minimum_energy_kwh": <num>}
3. "no_charge_window"        -> {"hours": [..]}
4. "no_discharge_window"     -> {"hours": [..]}
5. "max_grid_window"         -> {"hours": [..], "max_grid_kwh": <num>}
6. "no_op"                   -> structured_adjustment MUST be null, applies=false

RULES:
- Time ranges: the START hour is INCLUDED, the END hour is EXCLUDED.
  "1 PM to 3 PM" => [13, 14]. "2 PM to 4 PM" => [14, 15].
- Convert clock times to 24-hour integers (1 PM = 13, 3 PM = 15).
- "hours" must be unique, ascending integers in 0..23.
- If a note does not affect the 24-hour schedule, use directive_type "no_op",
  applies=false, structured_adjustment=null.
- For every non-no_op directive, applies MUST be true.
- Do NOT invent directive types, demand, solar, tariff, or battery values.
- Do NOT add constraints that are not in the note.
- Return ONLY the JSON object, no prose, no markdown fences.
"""


def _build_user_prompt(notes: List[str]) -> str:
    lines = ["Operator notes:"]
    for i, note in enumerate(notes):
        lines.append(f"{i}: {note}")
    lines.append("")
    lines.append(
        f"Return exactly {len(notes)} interpretation entries in note_index order."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Provider base
# ---------------------------------------------------------------------------
class LLMProvider:
    """Abstract provider. Subclasses return raw interpretation dicts."""

    name = "base"

    def interpret(self, notes: List[str]) -> List[dict]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (also works with any compatible base URL)
# ---------------------------------------------------------------------------
class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, temperature: float,
                 timeout: float):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def interpret(self, notes: List[str]) -> List[dict]:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(notes)},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # pragma: no cover - network
            raise RuntimeError(f"LLM provider request failed: {exc}") from exc

        content = body["choices"][0]["message"]["content"]
        return _extract_interpretations(content)


# ---------------------------------------------------------------------------
# Google Gemini provider
# ---------------------------------------------------------------------------
class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, temperature: float, timeout: float):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def interpret(self, notes: List[str]) -> List[dict]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": _build_user_prompt(notes)}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # pragma: no cover - network
            raise RuntimeError(f"LLM provider request failed: {exc}") from exc

        content = body["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_interpretations(content)


# ---------------------------------------------------------------------------
# Offline dev fallback (NOT a real LLM)
# ---------------------------------------------------------------------------
class OfflineFallbackProvider(LLMProvider):
    """
    Deterministic heuristic parser for LOCAL DEVELOPMENT ONLY.

    This is explicitly NOT a real LLM.  It exists so the pipeline can be
    exercised without an API key.  It uses keyword + number heuristics (not
    exact string matching) to approximate the directives.  It must never be
    presented as real LLM interpretation in judge/production mode.
    """

    name = "offline-fallback"

    _SOLAR = ("solar", "pv", "photovoltaic", "panel", "rooftop")
    _BATTERY = ("battery", "storage", "reserve", "soc", "state of charge")
    _DISCHARGE = ("discharge", "discharging", "draw", "drain")
    _GRID = ("grid", "import", "utility", "mains", "demand limit", "cap")

    def interpret(self, notes: List[str]) -> List[dict]:
        results: List[dict] = []
        for i, note in enumerate(notes):
            results.append(self._interpret_one(i, note))
        return results

    def _interpret_one(self, idx: int, note: str) -> dict:
        text = note.lower()
        hours = _extract_hours(text)

        # --- solar reduction ---
        if any(k in text for k in self._SOLAR) and _mentions_reduction(text):
            factor = _extract_solar_factor(text)
            if hours and factor is not None:
                return {
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": hours, "factor": factor},
                    "explanation": "Solar output is reduced during the given hours.",
                }

        # --- battery reserve ---
        if any(k in text for k in self._BATTERY) and (
            "reserve" in text or "at least" in text or "minimum" in text
            or "keep" in text or "maintain" in text
        ):
            reserve = _extract_energy_value(text)
            if hours and reserve is not None:
                return {
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "minimum_battery_reserve",
                    "structured_adjustment": {
                        "hours": hours,
                        "minimum_energy_kwh": reserve,
                    },
                    "explanation": "Battery must stay at or above the reserve.",
                }

        # --- no discharge window (checked BEFORE charge: "discharge" contains
        #     the substring "charge", so ordering matters) ---
        is_discharge = "discharg" in text
        is_charge = ("charg" in text) and not is_discharge

        if is_discharge and _mentions_prohibition(text):
            if hours:
                return {
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "no_discharge_window",
                    "structured_adjustment": {"hours": hours},
                    "explanation": "Battery discharging is not allowed in these hours.",
                }

        # --- no charge window ---
        if is_charge and _mentions_prohibition(text):
            if hours:
                return {
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "no_charge_window",
                    "structured_adjustment": {"hours": hours},
                    "explanation": "Battery charging is not allowed in these hours.",
                }

        # --- max grid window ---
        if any(k in text for k in self._GRID) and (
            "max" in text or "limit" in text or "cap" in text
            or "not exceed" in text or "no more than" in text
        ):
            cap = _extract_energy_value(text)
            if hours and cap is not None:
                return {
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "max_grid_window",
                    "structured_adjustment": {"hours": hours, "max_grid_kwh": cap},
                    "explanation": "Grid import is capped during these hours.",
                }

        # --- default: no_op ---
        return {
            "note_index": idx,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "This note does not affect the energy schedule.",
        }


# ---------------------------------------------------------------------------
# Heuristic helpers for the offline fallback
# ---------------------------------------------------------------------------
def _mentions_reduction(text: str) -> bool:
    return any(
        k in text
        for k in ("reduc", "drop", "lower", "less", "curtail", "degrad",
                  "maintenance", "washing", "one-fifth", "fraction", "shade",
                  "cloud", "outage", "down")
    )


def _mentions_prohibition(text: str) -> bool:
    return any(
        k in text
        for k in ("no ", "not ", "cannot", "can't", "unavailable", "prohibit",
                  "forbid", "disallow", "block", "prevent", "avoid", "without")
    )


# Word numbers that may appear in operator notes (e.g. "one until three").
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def _normalize_word_numbers(text: str) -> str:
    """Replace whole-word number words with digits (e.g. 'three' -> '3')."""
    pattern = r"\b(" + "|".join(
        sorted(_WORD_NUMBERS, key=len, reverse=True)
    ) + r")\b"
    return re.sub(pattern, lambda m: str(_WORD_NUMBERS[m.group(0)]), text)


def _extract_hours(text: str) -> List[int]:
    """
    Extract an ascending list of hours from a time range or explicit list.

    Handles: "1 PM to 3 PM", "1-3 PM", "13:00 and 15:00",
    "between 6 PM and 8 PM", "from one until three", "hours 18,19,20".
    Start inclusive, end exclusive.
    """
    t = _normalize_word_numbers(text.lower())

    # Explicit hour list: "hours 18, 19, 20" or "at 14 and 15"
    list_match = re.search(
        r"(?:hours?|at)\s*((?:\d{1,2}\s*(?:,|and|&)\s*)+\d{1,2})", t
    )
    if list_match:
        nums = [int(n) for n in re.findall(r"\d{1,2}", list_match.group(1))]
        nums = [n for n in nums if 0 <= n <= 23]
        if nums:
            return sorted(set(nums))

    # Range: "1 pm to 3 pm", "1-3 pm", "13:00 and 15:00",
    # "between 6 PM and 8 PM", "from 1 until 3".
    # A meridiem may appear on both ends or only one; if only one is given
    # it applies to both ends.
    range_match = re.search(
        r"(\d{1,2})(?::\d{2})?\s*(am|pm)?\s*"
        r"(?:to|until|through|till|and|-)\s*"
        r"(\d{1,2})(?::\d{2})?\s*(am|pm)?",
        t,
    )
    if range_match:
        start_raw, start_mer, end_raw, end_mer = range_match.groups()
        start = int(start_raw)
        end = int(end_raw)
        if start_mer and end_mer:
            start = _to_24h(start, start_mer)
            end = _to_24h(end, end_mer)
        elif start_mer or end_mer:
            mer = start_mer or end_mer
            start = _to_24h(start, mer)
            end = _to_24h(end, mer)
        if 0 <= start <= 23 and 0 <= end <= 23:
            return _range_hours(start, end)

    # Single am/pm time
    single = re.search(r"(\d{1,2})\s*(am|pm)", t)
    if single:
        h = _to_24h(int(single.group(1)), single.group(2))
        return [h]

    return []


def _to_24h(hour: int, meridiem: str) -> int:
    hour = hour % 12
    if meridiem == "pm":
        hour += 12
    return hour % 24


def _range_hours(start: int, end: int) -> List[int]:
    """Start inclusive, end exclusive. Handles wrap-around."""
    if end <= start:
        end += 24
    return [h % 24 for h in range(start, end)]


def _extract_solar_factor(text: str) -> Optional[float]:
    """Return the fraction of solar that REMAINS (0..1)."""
    # "80% reduction" -> 0.2
    m = re.search(r"(\d{1,3})\s*%\s*(?:reduction|less|lower|drop|decrease)", text)
    if m:
        return max(0.0, min(1.0, 1.0 - int(m.group(1)) / 100.0))
    # "drop to 20%" / "at 20%" -> 0.2
    m = re.search(r"(?:to|at|about|roughly|around)\s*(\d{1,3})\s*%", text)
    if m:
        return max(0.0, min(1.0, int(m.group(1)) / 100.0))
    # "one-fifth" -> 0.2
    fractions = {
        "one-fifth": 0.2, "one fifth": 0.2, "a fifth": 0.2,
        "one-quarter": 0.25, "one quarter": 0.25, "a quarter": 0.25,
        "one-third": 1 / 3, "one third": 1 / 3, "a third": 1 / 3,
        "one-half": 0.5, "one half": 0.5, "half": 0.5,
    }
    for phrase, value in fractions.items():
        if phrase in text:
            return value
    # "20% of normal" -> 0.2
    m = re.search(r"(\d{1,3})\s*%\s*of", text)
    if m:
        return max(0.0, min(1.0, int(m.group(1)) / 100.0))
    return None


def _extract_energy_value(text: str) -> Optional[float]:
    """Extract a kWh value from text like '120 kWh' or '100 kwh'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*kwh", text)
    if m:
        return float(m.group(1))
    # Fall back to a bare number if it looks like a magnitude.
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _extract_interpretations(content: str) -> List[dict]:
    """Parse the LLM's JSON content into a list of interpretation dicts."""
    if isinstance(content, list):
        return content
    text = content.strip()
    # Strip markdown fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}") from exc

    if isinstance(parsed, dict):
        for key in ("interpretations", "directives", "results", "data"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # Single-entry object.
        if "note_index" in parsed:
            return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise RuntimeError("LLM JSON did not contain an interpretations list")


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
def get_provider() -> LLMProvider:
    """Return the configured provider, or the offline fallback."""
    if settings.llm_is_configured():
        if settings.llm_provider == "openai":
            return OpenAICompatibleProvider(
                api_key=settings.llm_api_key,
                model=settings.resolved_model(),
                base_url=settings.resolved_base_url() or "https://api.openai.com/v1",
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_seconds,
            )
        if settings.llm_provider == "gemini":
            return GeminiProvider(
                api_key=settings.llm_api_key,
                model=settings.resolved_model(),
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_seconds,
            )

    if settings.allow_llm_fallback:
        logger.warning(
            "No LLM provider configured; using OFFLINE DEV FALLBACK "
            "(not a real LLM). Set LLM_PROVIDER/LLM_API_KEY for real "
            "interpretation, or ALLOW_LLM_FALLBACK=false to disable."
        )
        return OfflineFallbackProvider()

    raise RuntimeError(
        "No LLM provider configured and ALLOW_LLM_FALLBACK is disabled. "
        "Set LLM_PROVIDER and LLM_API_KEY."
    )


def interpret_notes(notes: List[str]) -> List[dict]:
    """
    Interpret operator notes into raw (untrusted) directive dicts.

    The result is validated by guardrails.py before use.

    Resilience: if a REAL provider (e.g. Mistral via the OpenAI-compatible
    endpoint) fails — timeout, network error, HTTP error, or malformed output —
    and ALLOW_LLM_FALLBACK is enabled, we fall back to the deterministic offline
    parser instead of surfacing an uncontrolled 500.  When ALLOW_LLM_FALLBACK is
    false the failure is re-raised (explicit opt-in to "fail loudly").
    """
    provider = get_provider()
    logger.info("Interpreting %d note(s) with provider=%s", len(notes), provider.name)
    try:
        return provider.interpret(notes)
    except Exception as exc:  # noqa: BLE001 - controlled provider failure
        if settings.allow_llm_fallback and provider.name != OfflineFallbackProvider.name:
            logger.warning(
                "LLM provider %s failed (%s); using deterministic offline "
                "fallback for %d note(s).",
                provider.name, exc, len(notes),
            )
            return OfflineFallbackProvider().interpret(notes)
        raise
