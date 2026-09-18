# ⚡ GridWise — AI-Assisted Energy Optimization

GridWise is an intelligent energy optimization system designed to optimize
grid electricity usage, solar generation, and battery storage using
constraint-based optimization and LLM-assisted operator note interpretation.

The system converts natural-language operator instructions into structured
energy directives and applies them to a 24-hour energy optimization plan.

---

## 🚀 Live Demo

### Railway Production API
https://gridwise-production-f810.up.railway.app

### API Documentation
https://gridwise-production-f810.up.railway.app/docs

### Health Check
https://gridwise-production-f810.up.railway.app/health

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
- 🔗 GitHub → Railway automatic deployment
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
