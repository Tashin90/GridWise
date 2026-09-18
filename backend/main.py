"""
GridWise — Smart Campus Energy Optimization API.

Entry point for the FastAPI service.

Endpoints
---------
GET  /health          -> {"status": "ok"}
POST /optimize-energy -> interpret operator notes (LLM), apply deterministic
                         guardrails, optimize the 24-hour schedule, validate
                         it by independent replay, and return the plan.

The heavy lifting lives in the sibling modules:
    config.py         -> environment/settings
    models.py         -> Pydantic request/response schemas
    llm_interpreter.py-> LLM interpretation of operator notes
    guardrails.py     -> deterministic validation of LLM output
    optimizer.py      -> OR-Tools energy optimization
    validator.py      -> independent replay validation of the final plan
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .guardrails import GuardrailError, validated_directives_to_interpretations
from .llm_interpreter import interpret_notes
from .models import OptimizeResponse, ScenarioRequest
from .optimizer import InfeasibleError, build_effective_constraints, optimize
from .validator import ValidationError as PlanValidationError, validate_plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gridwise")

app = FastAPI(
    title="GridWise API",
    description="Smart Campus Energy Optimization backend.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by the judge and by Docker."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Error handling: never leak stack traces or secrets
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def _on_request_validation_error(
    request: Request, exc: RequestValidationError
):
    """
    FastAPI raises RequestValidationError (default status 422) when the JSON
    body is malformed, missing, or structurally invalid.  Per the GridWise
    spec we classify all of those as HTTP 400.
    """
    logger.info("Request body validation failed: %s", exc.errors())
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Malformed or structurally invalid request body.",
            "errors": _safe_errors(exc),
        },
    )


@app.exception_handler(Exception)
async def _on_unhandled(request: Request, exc: Exception):
    """Controlled 500 — log internally, return a safe message."""
    logger.exception("Unhandled error while processing request")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------
def run_pipeline(scenario: ScenarioRequest) -> OptimizeResponse:
    """
    Full pipeline: LLM interpretation -> guardrails -> optimization ->
    independent validation -> response.

    Raises:
        GuardrailError        -> semantic problem with LLM output (422)
        InfeasibleError       -> no feasible schedule (422)
        PlanValidationError   -> generated plan failed replay (422)
    """
    # 1) LLM interpretation (must actually interpret the notes).
    raw_interpretations = interpret_notes(scenario.operator_notes)

    # 2) Deterministic guardrails: validate and normalise LLM output.
    directives = validated_directives_to_interpretations(
        raw_interpretations, scenario.operator_notes, scenario.battery
    )

    # 3) Apply directives to build the effective optimization constraints.
    constraints = build_effective_constraints(scenario, directives)

    # 4) Optimize the schedule.
    plan = optimize(scenario, constraints)

    # 5) Independent replay validation + recomputed totals.
    report = validate_plan(scenario, constraints, directives, plan)

    summary = _build_plan_summary(scenario, directives, report.totals)

    return OptimizeResponse(
        scenario_id=scenario.scenario_id,
        directive_interpretation=[d.to_interpretation() for d in directives],
        hourly_plan=plan,
        total_grid_kwh=report.totals.total_grid_kwh,
        total_cost_bdt=report.totals.total_cost_bdt,
        peak_grid_kwh=report.totals.peak_grid_kwh,
        plan_summary=summary,
    )


def _build_plan_summary(scenario, directives, totals) -> str:
    """Short human-readable description of the final strategy."""
    applied = [d for d in directives if d.applies and d.directive_type != "no_op"]
    if applied:
        names = ", ".join(sorted({d.directive_type for d in applied}))
        directive_text = f"Applied operator directives: {names}."
    else:
        directive_text = "No applicable operator directives; cost-only optimization."

    return (
        f"{directive_text} "
        f"Total grid usage {totals.total_grid_kwh:.2f} kWh, "
        f"peak {totals.peak_grid_kwh:.2f} kWh, "
        f"estimated cost {totals.total_cost_bdt:.2f} BDT. "
        "Battery returns to its initial energy at the end of the day."
    )


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(scenario: ScenarioRequest) -> OptimizeResponse:
    """
    Accept one scenario JSON body and return the interpretation + 24-hour plan.

    The request body is declared as the Pydantic model ``ScenarioRequest`` so
    it is fully documented in Swagger UI / OpenAPI (with a request body and
    example JSON).

    Status codes:
        200 success
        400 malformed / structurally invalid body
        422 semantic validation error (bad LLM output, infeasible schedule)
        500 controlled internal error
    """
    # Structural validation is handled by FastAPI/Pydantic before this
    # function is called; failures raise RequestValidationError -> 400.
    try:
        result = run_pipeline(scenario)
    except GuardrailError as exc:
        logger.warning("Guardrail rejection: %s", exc)
        return JSONResponse(
            status_code=422,
            content={"detail": f"LLM interpretation rejected: {exc}"},
        )
    except InfeasibleError as exc:
        logger.warning("Optimization infeasible: %s", exc)
        return JSONResponse(
            status_code=422,
            content={"detail": f"No feasible schedule: {exc}"},
        )
    except PlanValidationError as exc:
        logger.error("Generated plan failed validation: %s", exc)
        return JSONResponse(
            status_code=422,
            content={"detail": f"Generated plan failed validation: {exc}"},
        )

    return result


def _safe_errors(exc) -> list[dict]:
    """Return Pydantic errors without leaking internal objects."""
    safe = []
    for err in exc.errors():
        safe.append(
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "msg": str(err.get("msg", "invalid")),
                "type": str(err.get("type", "value_error")),
            }
        )
    return safe


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)