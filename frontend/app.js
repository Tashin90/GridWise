/* GridWise frontend — health check, scenario form, API calls, SVG charts. */
"use strict";

const API_DEFAULT = "http://127.0.0.1:8000";
const HOURS = 24;
const DEMO_SOLAR = [0,0,0,0,0,0,10,40,90,150,200,230,250,240,210,160,100,50,15,0,0,0,0,0];
const DEMO_DEMAND = new Array(HOURS).fill(180);
const DEMO_NOTES = [
  "Battery charging is not allowed from 2 PM to 4 PM.",
  "Expect an 80% reduction in rooftop solar during the 1-3 PM window.",
  "The campus will host a seminar today.",
];
const state = { apiBase: API_DEFAULT, busy: false };

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => Number.isFinite(n)
  ? Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  : "—";

function el(tag, attrs = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v != null) n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}

/* ---------------- health ---------------- */
async function checkHealth() {
  const b = $("healthBadge"), t = b.querySelector(".health-text");
  b.className = "health-badge health-unknown"; t.textContent = "Checking…";
  try {
    const r = await fetch(`${state.apiBase}/health`);
    const d = await r.json();
    if (!r.ok || d.status !== "ok") throw new Error();
    b.className = "health-badge health-ok"; t.textContent = "Backend online";
  } catch { b.className = "health-badge health-bad"; t.textContent = "Backend offline"; }
}

/* ---------------- form ---------------- */
function buildHours() {
  const body = $("hoursBody"); body.innerHTML = "";
  for (let h = 0; h < HOURS; h++) {
    const d = el("input", { type: "number", min: "0", step: "0.1", id: `demand-${h}`, value: DEMO_DEMAND[h] });
    const s = el("input", { type: "number", min: "0", step: "0.1", id: `solar-${h}`, value: DEMO_SOLAR[h] });
    body.appendChild(el("tr", {}, [
      el("td", { class: "hour-cell", text: String(h).padStart(2, "0") + ":00" }),
      el("td", {}, [d]), el("td", {}, [s]),
    ]));
  }
}

function addNote(v = "") {
  const list = $("notesList");
  if (list.children.length >= 3) return;
  const inp = el("input", { type: "text", placeholder: "e.g. Do not discharge the battery between 6 PM and 8 PM.", value: v });
  const rm = el("button", { type: "button", class: "note-remove", title: "Remove", text: "×",
    onclick: () => { row.remove(); syncNotes(); } });
  const row = el("div", { class: "note-row" }, [inp, rm]);
  list.appendChild(row); syncNotes();
}
const syncNotes = () => { $("addNoteBtn").disabled = $("notesList").children.length >= 3; };
const getNotes = () => Array.from($("notesList").querySelectorAll("input")).map(i => i.value.trim()).filter(Boolean);

function loadDemo() {
  $("scenarioId").value = "GRID-DEMO-001"; $("tariff").value = "7.00";
  $("capKwh").value = "500"; $("initKwh").value = "200"; $("minKwh").value = "50";
  $("maxCharge").value = "100"; $("maxDischarge").value = "100";
  for (let h = 0; h < HOURS; h++) { $(`demand-${h}`).value = DEMO_DEMAND[h]; $(`solar-${h}`).value = DEMO_SOLAR[h]; }
  $("notesList").innerHTML = ""; DEMO_NOTES.forEach(addNote);
}
function resetForm() {
  $("scenarioForm").reset(); $("notesList").innerHTML = ""; addNote(""); buildHours(); syncNotes();
}

/* ---------------- payload + API ---------------- */
function buildPayload() {
  const id = $("scenarioId").value.trim();
  const tariff = parseFloat($("tariff").value);
  const notes = getNotes();
  if (!id) throw new Error("Scenario ID is required.");
  if (!Number.isFinite(tariff) || tariff < 0) throw new Error("Tariff must be a non-negative number.");
  if (notes.length < 1 || notes.length > 3) throw new Error("Provide 1 to 3 operator notes.");
  const hours = [];
  for (let h = 0; h < HOURS; h++) {
    const d = parseFloat($(`demand-${h}`).value), s = parseFloat($(`solar-${h}`).value);
    if (!Number.isFinite(d) || d < 0) throw new Error(`Hour ${h}: demand must be a non-negative number.`);
    if (!Number.isFinite(s) || s < 0) throw new Error(`Hour ${h}: solar must be a non-negative number.`);
    hours.push({ hour: h, demand_kwh: d, solar_kwh: s, tariff_bdt_per_kwh: tariff });
  }
  const battery = {
    capacity_kwh: parseFloat($("capKwh").value), initial_energy_kwh: parseFloat($("initKwh").value),
    minimum_energy_kwh: parseFloat($("minKwh").value),
    max_charge_kwh_per_hour: parseFloat($("maxCharge").value),
    max_discharge_kwh_per_hour: parseFloat($("maxDischarge").value),
  };
  for (const [k, v] of Object.entries(battery))
    if (!Number.isFinite(v) || v < 0) throw new Error(`Battery field "${k}" must be a non-negative number.`);
  return { scenario_id: id, operator_notes: notes, hours, battery };
}

async function callOptimize(payload) {
  const r = await fetch(`${state.apiBase}/optimize-energy`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  let d = null; try { d = await r.json(); } catch {}
  if (!r.ok) { const e = new Error((d && d.detail) || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return d;
}

/* ---------------- render ---------------- */
function renderKPIs(res) {
  const plan = res.hourly_plan || [];
  const solar = plan.reduce((a, p) => a + (p.solar_used_kwh || 0), 0);
  const finalE = plan.length ? plan[plan.length - 1].battery_energy_after_kwh : 0;
  $("kpiCost").textContent = fmt(res.total_cost_bdt);
  $("kpiGrid").textContent = fmt(res.total_grid_kwh);
  $("kpiPeak").textContent = fmt(res.peak_grid_kwh);
  $("kpiSolar").textContent = fmt(solar);
  $("kpiBattery").textContent = fmt(finalE);
}

function renderDirectives(res) {
  const wrap = $("directivesTable"); wrap.innerHTML = "";
  const items = res.directive_interpretation || [];
  if (!items.length) { wrap.appendChild(el("p", { class: "muted", text: "No directives returned." })); return; }
  const tb = el("tbody");
  items.forEach(d => tb.appendChild(el("tr", {}, [
    el("td", { text: String(d.note_index) }),
    el("td", {}, [el("span", { class: "chip chip-type", text: d.directive_type })]),
    el("td", {}, [el("span", { class: d.applies ? "chip chip-applies" : "chip chip-noop", text: d.applies ? "applies" : "no-op" })]),
    el("td", { class: "num", text: d.structured_adjustment ? JSON.stringify(d.structured_adjustment) : "—" }),
    el("td", { text: d.explanation || "" }),
  ])));
  wrap.appendChild(el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Note #", "Directive", "Status", "Structured Adjustment", "Explanation"].map(h => el("th", { text: h })))]),
    tb,
  ]));
}

function renderPlan(res) {
  const body = $("planBody"); body.innerHTML = "";
  (res.hourly_plan || []).forEach(p => body.appendChild(el("tr", {}, [
    el("td", { class: "num", text: String(p.hour).padStart(2, "0") + ":00" }),
    el("td", { class: "num", text: fmt(p.grid_kwh) }),
    el("td", { class: "num", text: fmt(p.solar_used_kwh) }),
    el("td", {}, [el("span", { class: `badge badge-${p.battery_action}`, text: p.battery_action })]),
    el("td", { class: "num", text: fmt(p.battery_kwh) }),
    el("td", { class: "num", text: fmt(p.battery_energy_after_kwh) }),
  ])));
}

const NS = "http://www.w3.org/2000/svg";
const svg = (t, a = {}) => { const n = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) n.setAttribute(k, v); return n; };

function renderEnergyChart(res) {
  const host = $("energyChart"); host.innerHTML = "";
  const plan = res.hourly_plan || []; if (!plan.length) return;
  const demand = plan.map(p => p.grid_kwh + p.solar_used_kwh);
  const solar = plan.map(p => p.solar_used_kwh), grid = plan.map(p => p.grid_kwh);
  const W = 900, H = 300, pL = 46, pR = 12, pT = 14, pB = 34, pw = W - pL - pR, ph = H - pT - pB;
  const max = Math.max(1, ...demand, ...solar, ...grid), nice = Math.ceil(max / 50) * 50;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H, role: "img" });
  for (let i = 0; i <= 5; i++) {
    const v = nice / 5 * i, y = pT + ph - v / nice * ph;
    s.appendChild(svg("line", { x1: pL, y1: y, x2: W - pR, y2: y, stroke: "#27365c" }));
    s.appendChild(svg("text", { x: pL - 8, y: y + 4, "text-anchor": "end", fill: "#9db0d4", "font-size": 11 })).textContent = Math.round(v);
  }
  const gw = pw / HOURS, bw = Math.max(2, (gw - 4) / 3);
  const series = [[demand, "#64748b"], [solar, "#fbbf24"], [grid, "#38bdf8"]];
  for (let h = 0; h < HOURS; h++) {
    series.forEach(([data, color], si) => {
      const bh = (data[h] || 0) / nice * ph;
      s.appendChild(svg("rect", { x: pL + h * gw + 2 + si * bw, y: pT + ph - bh, width: bw, height: Math.max(0, bh), fill: color, rx: 1.5 }));
    });
    if (h % 3 === 0) s.appendChild(svg("text", { x: pL + h * gw + gw / 2, y: H - 12, "text-anchor": "middle", fill: "#9db0d4", "font-size": 10 })).textContent = String(h).padStart(2, "0");
  }
  host.appendChild(s);
}

function renderBatteryChart(res) {
  const host = $("batteryChart"); host.innerHTML = "";
  const plan = res.hourly_plan || []; if (!plan.length) return;
  const soc = plan.map(p => p.battery_energy_after_kwh);
  const W = 900, H = 220, pL = 46, pR = 12, pT = 14, pB = 34, pw = W - pL - pR, ph = H - pT - pB;
  const nice = Math.ceil(Math.max(1, ...soc) / 50) * 50;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H, role: "img" });
  for (let i = 0; i <= 4; i++) {
    const v = nice / 4 * i, y = pT + ph - v / nice * ph;
    s.appendChild(svg("line", { x1: pL, y1: y, x2: W - pR, y2: y, stroke: "#27365c" }));
    s.appendChild(svg("text", { x: pL - 8, y: y + 4, "text-anchor": "end", fill: "#9db0d4", "font-size": 11 })).textContent = Math.round(v);
  }
  const gw = pw / HOURS;
  const color = a => a === "charge" ? "#34d399" : a === "discharge" ? "#fb7185" : "#64748b";
  for (let h = 0; h < HOURS; h++) {
    s.appendChild(svg("rect", { x: pL + h * gw + 1, y: pT + ph + 6, width: Math.max(2, gw - 2), height: 14, fill: color(plan[h].battery_action), rx: 2 }));
    if (h % 3 === 0) s.appendChild(svg("text", { x: pL + h * gw + gw / 2, y: H - 6, "text-anchor": "middle", fill: "#9db0d4", "font-size": 10 })).textContent = String(h).padStart(2, "0");
  }
  const pts = soc.map((v, h) => `${pL + h * gw + gw / 2},${pT + ph - v / nice * ph}`).join(" ");
  s.appendChild(svg("polyline", { points: pts, fill: "none", stroke: "#a78bfa", "stroke-width": 2.5, "stroke-linejoin": "round" }));
  soc.forEach((v, h) => s.appendChild(svg("circle", { cx: pL + h * gw + gw / 2, cy: pT + ph - v / nice * ph, r: 2.4, fill: "#a78bfa" })));
  host.appendChild(s);
}

/* ---------------- UI state ---------------- */
function setBusy(b) {
  state.busy = b;
  const btn = $("optimizeBtn");
  btn.disabled = b; btn.querySelector(".spinner").hidden = !b;
  btn.querySelector(".btn-label").textContent = b ? "Optimizing…" : "Optimize Energy";
}
const showError = (m) => { const x = $("errorBox"); x.textContent = m; x.hidden = false; };
const clearError = () => { const x = $("errorBox"); x.hidden = true; x.textContent = ""; };

function showResults(res) {
  $("emptyState").hidden = true; $("results").hidden = false;
  renderKPIs(res); $("planSummary").textContent = res.plan_summary || "—";
  $("summaryScenario").textContent = res.scenario_id || "—";
  renderDirectives(res); renderEnergyChart(res); renderBatteryChart(res); renderPlan(res);
  $("statusLine").textContent = `Scenario "${res.scenario_id}" optimized · ${(res.hourly_plan || []).length} hours`;
}

async function onSubmit(e) {
  e.preventDefault(); if (state.busy) return; clearError();
  let payload; try { payload = buildPayload(); } catch (err) { showError(err.message); return; }
  setBusy(true); $("statusLine").textContent = "Sending scenario to the optimizer…";
  try { showResults(await callOptimize(payload)); }
  catch (err) { showError(`Optimization failed${err.status ? ` (HTTP ${err.status})` : ""}: ${err.message}`); $("statusLine").textContent = "Optimization failed."; }
  finally { setBusy(false); }
}

function init() {
  buildHours(); addNote(DEMO_NOTES[0]); syncNotes();
  $("scenarioForm").addEventListener("submit", onSubmit);
  $("demoBtn").addEventListener("click", () => { loadDemo(); clearError(); });
  $("resetBtn").addEventListener("click", () => { resetForm(); clearError(); });
  $("addNoteBtn").addEventListener("click", () => addNote(""));
  const api = $("apiBase");
  api.addEventListener("change", () => {
    state.apiBase = api.value.trim().replace(/\/+$/, "") || API_DEFAULT;
    api.value = state.apiBase; checkHealth();
  });
  checkHealth(); setInterval(checkHealth, 15000);
}
document.addEventListener("DOMContentLoaded", init);