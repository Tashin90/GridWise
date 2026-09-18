# GridWise — Smart Campus Energy Optimization

**BUP CSE Fest 2026 Hackathon — LLM-Assisted Operator Directive Interpretation**

GridWise receives a 24-hour energy scenario plus 1–3 natural-language operator
notes. It uses an **LLM** to interpret each note into a structured directive,
validates that interpretation deterministically, applies it to an energy
optimization problem, solves for the minimum-cost schedule, independently
re-validates the result, and returns the machine-checkable interpretation and
the final 24-hour plan.

The LLM is a **first-class part of the interpretation path** — it is not just
used for cosmetic summary text.

---

## 1. Problem explanation

Each request contains:

- `scenario_id` — scenario identifier
- `operator_notes` — 1 to 3 free-text notes
- `hours` — exactly 24 hourly records (`hour`, `demand_kwh`, `solar_kwh`,
  `tariff_bdt_per_kwh`)
- `battery` — capacity, initial/minimum energy, max charge/discharge per hour

The system must:

1. Understand every operator note using an LLM.
2. Convert applicable notes into one supported structured directive.
3. Convert irrelevant notes into `no_op`.
4. Validate the LLM output deterministically.
5. Apply every valid directive.
6. Generate a valid 24-hour energy schedule.
7. Minimize total grid cost while satisfying every energy, battery, and
   operator directive constraint.
8. Return the required interpretation + plan JSON.

---

## 2. Architecture

```
GridWise/
├── backend/
│   ├── main.py            FastAPI app: /health, /optimize-energy, error handling
│   ├── models.py          Pydantic request/response + directive schemas
│   ├── config.py          Environment settings (LLM provider, keys, timeouts)
│   ├── llm_interpreter.py LLM provider abstraction + offline dev fallback
│   ├── guardrails.py      Deterministic validation of untrusted LLM output
│   ├── optimizer.py       OR-Tools CP-SAT MILP energy optimizer
│   ├── validator.py       Independent replay + recomputed totals
│   ├── requirements.txt   Python dependencies
│   └── __init__.py
├── frontend/              Zero-dependency dashboard (HTML/CSS/JS)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/                 pytest suite (health, interpreter, guardrails, optimizer, api)
├── conftest.py            Test fixtures/scenario builder
├── .env.example           Example environment variables (no secrets)
├── .gitignore             Ignores .env and build artifacts
├── Dockerfile             Container image for deployment
└── README.md
```

## 3. Data flow

```
POST /optimize-energy
   │
   ▼
[1] Pydantic      → structural validation (400 on malformed input)
   │
   ▼
[2] llm_interpreter → LLM interprets each note (1:1, in note_index order)
   │
   ▼
[3] guardrails    → deterministic validation of untrusted LLM output (422 on failure)
   │
   ▼
[4] optimizer     → apply directives, build MILP, minimize cost (422 if infeasible)
   │
   ▼
[5] validator     → independent replay + recomputed totals (422 if invalid)
   │
   ▼
200 → { scenario_id, directive_interpretation, hourly_plan, totals..., plan_summary }
```

---

## 4. Supported directives

Only these six directive types are supported.

| Type | structured_adjustment | Meaning |
|------|----------------------|---------|
| `solar_reduction` | `{"hours":[...], "factor": 0..1}` | Reduce usable solar. `factor` is the **fraction that remains** (80% reduction → `0.2`). |
| `minimum_battery_reserve` | `{"hours":[...], "minimum_energy_kwh": n}` | Battery energy must stay ≥ `n` during those hours. |
| `no_charge_window` | `{"hours":[...]}` | Battery charge must be 0 during those hours. |
| `no_discharge_window` | `{"hours":[...]}` | Battery discharge must be 0 during those hours. |
| `max_grid_window` | `{"hours":[...], "max_grid_kwh": n}` | `grid_kwh ≤ n` during those hours. |
| `no_op` | `null` (and `applies=false`) | Note does not affect the schedule. |

**Time ranges:** start hour included, end hour excluded.
`1 PM to 3 PM → [13, 14]`, `2 PM to 4 PM → [14, 15]`.

---

## 5. API endpoints

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /optimize-energy`

Status codes: `200` success · `400` malformed/structurally invalid ·
`422` semantic validation error (bad LLM output / infeasible) · `500` controlled
internal error. Raw stack traces and secrets are never returned.

---

## 6. Request example

```json
{
  "scenario_id": "GRID-101",
  "operator_notes": [
    "Battery charging is not allowed from 2 PM to 4 PM.",
    "Expect an 80% reduction in rooftop solar during the 1-3 PM window."
  ],
  "hours": [
    { "hour": 0,  "demand_kwh": 180, "solar_kwh": 0,   "tariff_bdt_per_kwh": 7 },
    { "hour": 1,  "demand_kwh": 180, "solar_kwh": 0,   "tariff_bdt_per_kwh": 7 }
  ],
  "battery": {
    "capacity_kwh": 500,
    "initial_energy_kwh": 200,
    "minimum_energy_kwh": 50,
    "max_charge_kwh_per_hour": 100,
    "max_discharge_kwh_per_hour": 100
  }
}
```

> `hours` must contain exactly 24 entries (0..23). The example shows two for brevity.

## 7. Response example

```json
{
  "scenario_id": "GRID-101",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "no_charge_window",
      "structured_adjustment": { "hours": [14, 15] },
      "explanation": "Battery charging is not allowed in these hours."
    },
    {
      "note_index": 1,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": { "hours": [13, 14], "factor": 0.2 },
      "explanation": "Solar output is reduced during the given hours."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 180.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 200.0
    }
  ],
  "total_grid_kwh": 3210.0,
  "total_cost_bdt": 22470.0,
  "peak_grid_kwh": 180.0,
  "plan_summary": "Applied operator directives: no_charge_window, solar_reduction. ..."
}
```

Each `hourly_plan` item uses exactly one `battery_action`:
`charge`, `discharge`, or `idle`.

---

## 8. Local setup

Requires **Python 3.10+**.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
pip install pytest httpx        # for running the test suite
```

## 9. Environment variables

Copy `.env.example` to `.env` and fill in values. **Never commit `.env`.**

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | `openai` \| `gemini` \| `none` | `none` |
| `LLM_API_KEY` | API key for the provider | (empty) |
| `LLM_MODEL` | Model name | provider default |
| `LLM_BASE_URL` | Custom OpenAI-compatible base URL | provider default |
| `LLM_TEMPERATURE` | Sampling temperature | `0.0` |
| `LLM_TIMEOUT_SECONDS` | Request timeout | `30` |
| `ALLOW_LLM_FALLBACK` | Allow offline dev fallback when no key | `true` |
| `PORT` | Server port | `8000` |

**Required for real LLM interpretation:** `LLM_PROVIDER` **and** `LLM_API_KEY`.
Example (OpenAI):

```
LLM_PROVIDER=openai
LLM_API_KEY=sk-...your-key...
LLM_MODEL=gpt-4o-mini
```

---

## 10. How to run

From the repository root, start the server using the module form. This avoids
requiring the Python `Scripts` directory to be on your `PATH` (the bare
`uvicorn` command often fails with "not recognized"):

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Equivalent alternatives:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
python -m backend.main
```

> On Windows, if `python` is not on PATH either, use the full interpreter path,
> e.g. `& "C:\Path\To\Python312\python.exe" -m uvicorn backend.main:app --port 8000`.

Interactive docs: http://127.0.0.1:8000/docs

## 11. How to run tests

```bash
python -m pytest -q
```

The suite covers 20 areas (A–T): health, no-op scenarios, each directive,
multiple directives, paraphrases, battery/charge/discharge limits, solar
availability, energy balance, end-of-day neutrality, invalid/duplicate LLM
output, unsupported directive types, and status codes.

## 12. How to run Docker

```bash
docker build -t gridwise .
docker run -p 8000:8000 \
  -e LLM_PROVIDER=openai -e LLM_API_KEY=sk-... \
  gridwise
```

The container listens on `0.0.0.0` and uses the deployment-provided `PORT`.

## 13. Example curl commands

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @scenario.json
```

---

## 14. LLM interpretation

`llm_interpreter.py` defines a provider abstraction:

- `OpenAICompatibleProvider` — any OpenAI-compatible chat-completions endpoint.
- `GeminiProvider` — Google Gemini `generateContent`.
- `OfflineFallbackProvider` — **development only**, a deterministic heuristic
  parser used when no API key is configured. It is explicitly *not* a real LLM
  and must not be used in judge/production mode. Set `ALLOW_LLM_FALLBACK=false`
  to disable it and fail loudly instead.

The system prompt instructs the model to return exactly one interpretation per
note, in `note_index` order, using only the six supported directive types, with
start-inclusive/end-exclusive time ranges. Structured JSON output is requested
where the provider supports it.

## 15. Guardrails

`guardrails.py` treats LLM output as **untrusted** and rejects (422):
missing/duplicate/out-of-range `note_index`, non-ascending order, unsupported
directive types, wrong `applies` semantics, non-null `structured_adjustment`
for `no_op`, non-ascending/duplicate/out-of-range hours, solar factor outside
`[0,1]`, reserve above capacity, missing required fields, etc. It never invents
a rule and never crashes on malformed input.

## 16. Optimization

`optimizer.py` builds a **CP-SAT** (OR-Tools) integer model scaled by `10000`
for numerical stability and minimizes `Σ grid_kwh[h] · tariff[h]`. Constraints:
energy balance, solar availability, charge/discharge limits, battery bounds,
no simultaneous charge+discharge, and end-of-day neutrality (`E_after[23] ==
initial`). Directives adjust effective solar, per-hour minimums, charge/discharge
availability, and grid caps.

## 17. Final validation

`validator.py` independently **replays** the schedule: it recomputes battery
transitions, checks every energy equation, battery/capacity limits, solar usage,
end-of-day neutrality, and every directive; then recomputes `total_grid_kwh`,
`total_cost_bdt`, and `peak_grid_kwh` from scratch (the optimizer's totals are
never trusted). Any violation raises a controlled error.

---

## 18. Numerical precision

The solver uses a scale factor of `10000` (finer than the judge's ~0.01
tolerance), and the validator uses a `1e-4` tolerance. Internal precision is
preserved; only displayed values are rounded.

---

## 19. Frontend — Smart Campus Dashboard

A zero-dependency dashboard lives in `frontend/` (plain HTML/CSS/JS, no build
step, no npm). It lets an operator enter a scenario, send it to the optimizer,
and inspect the interpretation and the resulting plan.

```
frontend/
├── index.html   Layout: health badge, scenario form, results
├── styles.css   Dark responsive theme
└── app.js       Form handling, API calls, SVG charts
```

### Features

- **Backend health indicator** — polls `GET /health` every 15 s.
- **Scenario form** — `scenario_id`, 24 hourly demand/solar inputs, tariff,
  battery config (capacity, initial/minimum energy, max charge/discharge), and
  1–3 operator notes.
- **Load Demo** — fills a sample scenario (including the three example notes).
- **Optimize Energy** — validates inputs, `POST`s to `/optimize-energy`, and
  renders results; failures show inline error messages.
- **Results** — KPI cards (total cost, total grid, peak grid, solar used, final
  battery energy), a directive-interpretation table, a full 24-hour plan table,
  the plan summary, and SVG charts for hourly energy and battery state/actions.

### Running the frontend

Two terminals, both from the repository root:

```bash
# terminal 1 — backend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend static server
python -m http.server 5500 --directory frontend
```

Then open http://127.0.0.1:5500. Opening `frontend/index.html` directly in a
browser also works because the backend enables CORS (`allow_origins=["*"]`).
The API base URL is editable from the dashboard header; it defaults to
`http://127.0.0.1:8000`.

---

## 20. Deploy the backend to Railway

The repository already contains a `Dockerfile` and a `railway.json`, both wired
to bind to Railway's `PORT` environment variable.

### What Railway uses

- **Builder**: `DOCKERFILE` (see `railway.json`)
- **Build command**: `pip install --no-cache-dir -r backend/requirements.txt`
  (in the `Dockerfile`)
- **Start command**:
  `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
  (also set in `railway.json`; `PORT` is provided by Railway — do not hardcode 8000)
- **Health check path**: `/health`

### Steps

1. Push the repository to GitHub (ensure `.env` is NOT committed — it is already
   in `.gitignore`).
2. In Railway: **New Project → Deploy from GitHub repo** → select the repository.
3. Railway auto-detects `railway.json`/`Dockerfile` at the **repository root**.
   Keep the service root at the repository root (the Dockerfile copies
   `backend/`). Do not point the root at `backend/`.
4. Add the environment variables (Project → Variables):

   | Variable | Value |
   |----------|-------|
   | `LLM_PROVIDER` | `gemini` (or `openai`) |
   | `LLM_MODEL` | `gemini-1.5-flash` |
   | `LLM_API_KEY` | your provider key (Railway variable; never in code) |
   | `LLM_BASE_URL` | leave empty for gemini; set for OpenAI-compatible |
   | `ALLOW_LLM_FALLBACK` | `true` |

   `PORT` is set automatically by Railway; do not set it manually.
5. Deploy. Railwards builds the image and starts the server on `$PORT`.

### URLs (after deploy)

- Health check: `https://<your-app>.up.railway.app/health`
- Optimize endpoint: `POST https://<your-app>.up.railway.app/optimize-energy`
- Interactive docs: `https://<your-app>.up.railway.app/docs`

The frontend can point at the deployed backend by editing the **API** field in
the dashboard header to the Railway URL.
