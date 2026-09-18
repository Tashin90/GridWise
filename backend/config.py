"""
Application configuration.

All configuration comes from environment variables (loaded from a .env file
when present).  No secrets are ever hard-coded here.

Environment variables
---------------------
LLM_PROVIDER        : "openai" | "gemini" | "none"   (default: "none")
LLM_API_KEY         : API key for the selected provider
LLM_MODEL           : model name (provider-specific default if unset)
LLM_BASE_URL        : optional custom OpenAI-compatible base URL
LLM_TEMPERATURE     : sampling temperature (default 0.0 for determinism)
LLM_TIMEOUT_SECONDS : per-request timeout (default 30)
ALLOW_LLM_FALLBACK  : "true" to allow the offline dev fallback when no key
                      is configured (default: "true").  In judge/production
                      mode this should be "false" so we never pretend that
                      real LLM interpretation happened.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv missing is harmless
    pass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Default model per provider (only used when LLM_MODEL is not set).
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
}


@dataclass
class Settings:
    """Runtime settings, read once from the environment."""

    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "none").strip().lower()
    )
    llm_api_key: Optional[str] = field(
        default_factory=lambda: (os.getenv("LLM_API_KEY") or "").strip() or None
    )
    llm_model: str = field(
        default_factory=lambda: (os.getenv("LLM_MODEL") or "").strip()
    )
    llm_base_url: Optional[str] = field(
        default_factory=lambda: (os.getenv("LLM_BASE_URL") or "").strip() or None
    )
    llm_temperature: float = field(
        default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.0)
    )
    llm_timeout_seconds: float = field(
        default_factory=lambda: _get_float("LLM_TIMEOUT_SECONDS", 30.0)
    )
    allow_llm_fallback: bool = field(
        default_factory=lambda: _get_bool("ALLOW_LLM_FALLBACK", True)
    )
    # Numerical tolerance used across the solver and the validator.
    tolerance: float = 1e-6

    def resolved_model(self) -> str:
        """Return the effective model name for the active provider."""
        if self.llm_model:
            return self.llm_model
        return DEFAULT_MODELS.get(self.llm_provider, "")

    def resolved_base_url(self) -> Optional[str]:
        """Return the effective base URL for the active provider."""
        if self.llm_base_url:
            return self.llm_base_url
        return DEFAULT_BASE_URLS.get(self.llm_provider)

    def llm_is_configured(self) -> bool:
        """True when a real LLM provider and API key are available."""
        return self.llm_provider in DEFAULT_MODELS and bool(self.llm_api_key)


# Single shared settings instance.
settings = Settings()