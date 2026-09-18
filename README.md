# ⚡ GridWise — AI-Assisted Energy Optimization

GridWise is an intelligent energy optimization system designed to optimize
grid electricity usage, solar generation, and battery storage using
constraint-based optimization and LLM-assisted operator note interpretation.

The system converts natural-language operator instructions into structured
energy directives and applies them to a 24-hour energy optimization plan.

---

## ✨ Key Features

- ⚡ 24-hour energy optimization
- 🔋 Battery charging and discharging optimization
- ☀️ Solar generation handling
- 🌐 Grid electricity optimization
- 🤖 LLM-assisted operator note interpretation
- 🛡️ Guardrails for structured directives
- 🔄 Deterministic offline fallback
- 📊 Energy cost optimization
- 🚀 Railway cloud deployment
- 🔗 GitHub-based deployment
- 📡 REST API using FastAPI

---

## 🧠 How It Works

```text
Operator Notes
      │
      ▼
┌──────────────────────┐
│ LLM Interpretation   │
└──────────┬───────────┘
           │
           ▼
 Structured Directives
           │
           ▼
┌──────────────────────┐
│ Guardrails / Validate│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Energy Optimizer     │
│ CP-SAT / OR-Tools    │
└──────────┬───────────┘
           │
           ▼
  24-Hour Energy Plan
           │
           ▼
 Grid + Solar + Battery
