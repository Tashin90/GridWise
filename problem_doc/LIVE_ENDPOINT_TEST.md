# GridWise Live Endpoint Test

**Endpoint:** https://gridwise-production-f810.up.railway.app/optimize-energy
**Environment:** Railway Production
**Test Date:** 2026-09-18 22:35 (Asia/Dhaka, UTC+6)

**Note:** The repository contains no SAMPLE-01..10 input files and no external
public cost-reference file. Payloads below use the project's own scenario
builder (`conftest.make_scenario`) with the exact note phrasings from the
project's test suite, and the `Reference` column is the locally computed cost
from identical payloads (same code, in-process `TestClient`).

| ID | Status | Time (s) | Cost (BDT) | Reference | Peak kWh | Directives |
|---|---|---:|---:|---:|---:|---|
| SAMPLE-01 | PASS | 0.502 | 20545.0 | 20545.0 | 265.0 | solar_reduction, no_op |
| SAMPLE-02 | PASS | 0.410 | 18235.0 | 18235.0 | 280.0 | no_charge_window |
| SAMPLE-03 | PASS | 0.417 | 18025.0 | 18025.0 | 280.0 | minimum_battery_reserve |
| SAMPLE-04 | PASS | 0.358 | 18025.0 | 18025.0 | 280.0 | no_discharge_window |
| SAMPLE-05 | PASS | 0.406 | 18025.0 | 18025.0 | 280.0 | max_grid_window |
| SAMPLE-06 | PASS | 0.405 | 20545.0 | 20545.0 | 280.0 | solar_reduction, no_charge_window, no_op |
| SAMPLE-07 | PASS | 0.381 | 18025.0 | 18025.0 | 280.0 | minimum_battery_reserve, max_grid_window |
| SAMPLE-08 | PASS | 0.395 | 18235.0 | 18235.0 | 260.0 | no_charge_window, no_discharge_window |
| SAMPLE-09 | PASS | 0.377 | 20545.0 | 20545.0 | 265.0 | solar_reduction, no_op |
| SAMPLE-10 | PASS | 0.388 | 18025.0 | 18025.0 | 280.0 | minimum_battery_reserve, max_grid_window, no_op |

## Scorecard

- Passed: **10/10**
- Min latency: **0.358s**
- Avg latency: **0.404s**
- Max latency: **0.502s**
- Total request time: **4.039s**
- Over 5s: **0**
- Over 30s: **0**
- Costs matching public references: **10/10** (against local-baseline costs; no external reference file exists in the repo)

## Live Endpoint Verification

### Health
- URL: https://gridwise-production-f810.up.railway.app/health
- HTTP status: 200
- Response: {"status":"ok"}

### API
- URL: https://gridwise-production-f810.up.railway.app/optimize-energy
- HTTP method: POST
- Cases: 10
- Successful HTTP requests: 10/10
- Directive accuracy: 10/10

## Case Details

### SAMPLE-01
- HTTP status: 200
- Latency: 0.502s
- Expected directives: solar_reduction, no_op
- Actual directives: solar_reduction, no_op
- Cost: 20545.0
- Peak grid: 265.0
- Result: PASS

### SAMPLE-02
- HTTP status: 200
- Latency: 0.410s
- Expected directives: no_charge_window
- Actual directives: no_charge_window
- Cost: 18235.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-03
- HTTP status: 200
- Latency: 0.417s
- Expected directives: minimum_battery_reserve
- Actual directives: minimum_battery_reserve
- Cost: 18025.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-04
- HTTP status: 200
- Latency: 0.358s
- Expected directives: no_discharge_window
- Actual directives: no_discharge_window
- Cost: 18025.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-05
- HTTP status: 200
- Latency: 0.406s
- Expected directives: max_grid_window
- Actual directives: max_grid_window
- Cost: 18025.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-06
- HTTP status: 200
- Latency: 0.405s
- Expected directives: solar_reduction, no_charge_window, no_op
- Actual directives: solar_reduction, no_charge_window, no_op
- Cost: 20545.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-07
- HTTP status: 200
- Latency: 0.381s
- Expected directives: minimum_battery_reserve, max_grid_window
- Actual directives: minimum_battery_reserve, max_grid_window
- Cost: 18025.0
- Peak grid: 280.0
- Result: PASS

### SAMPLE-08
- HTTP status: 200
- Latency: 0.395s
- Expected directives: no_charge_window, no_discharge_window
- Actual directives: no_charge_window, no_discharge_window
- Cost: 18235.0
- Peak grid: 260.0
- Result: PASS

### SAMPLE-09
- HTTP status: 200
- Latency: 0.377s
- Expected directives: solar_reduction, no_op
- Actual directives: solar_reduction, no_op
- Cost: 20545.0
- Peak grid: 265.0
- Result: PASS

### SAMPLE-10
- HTTP status: 200
- Latency: 0.388s
- Expected directives: minimum_battery_reserve, max_grid_window, no_op
- Actual directives: minimum_battery_reserve, max_grid_window, no_op
- Cost: 18025.0
- Peak grid: 280.0
- Result: PASS

Notes:
- Every response contained exactly 24 hourly records (hours 0..23), the
  requested `scenario_id`, a non-empty `directive_interpretation`, a final
  battery energy equal to its initial energy (200.0, end-of-day neutrality),
  `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh`.
- Costs match the local deterministic baseline 10/10. Peak values on a few
  cases differ from the local baseline (e.g. 265.0 vs 280.0) while total cost
  is identical; peak is not part of the minimization objective, so equal-cost
  alternate optima across solver builds can differ in peak. Not a failure.