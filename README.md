# ⚡ GridWise — Campus Energy Optimization API

> 🏆 BUP CSE Fest 2026 Hackathon Project

GridWise is an AI-assisted campus energy optimization platform developed
for the BUP CSE Fest 2026 Hackathon.

The system converts natural-language operator instructions into structured
energy directives and applies them to a 24-hour constrained optimization
problem involving grid electricity, solar generation, and battery storage.

## 🚀 Live Deployment

**Platform:** Railway

**API:** Production REST API

### Available Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health check |
| POST | `/optimize-energy` | Generate optimized 24-hour energy plan |

## 🧠 Core Pipeline

Operator Notes
      ↓
LLM Interpretation
      ↓
Structured Directives
      ↓
Guardrails Validation
      ↓
Energy Optimization
      ↓
Schedule Validation
      ↓
24-Hour Energy Plan

## 🏆 Hackathon Benchmark

Cases: 10
Passed: 10/10
Accuracy: 100%

The benchmark evaluates natural-language directive interpretation and
validates the resulting 24-hour energy schedule.

## 🔐 Security

API keys and other secrets are stored using environment variables and are
never committed to GitHub or exposed through API responses.
