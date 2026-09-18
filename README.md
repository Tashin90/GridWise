# GridWise ⚡

### AI-Assisted Energy Optimization Platform

GridWise is an intelligent energy optimization platform that combines
**Natural Language Processing, LLM-assisted directive interpretation,**
**validation guardrails, and constraint-based optimization** to generate
feasible 24-hour energy schedules.

The system allows operators to provide energy-related instructions in
natural language. These instructions are interpreted into structured
directives and then incorporated into the optimization process while
maintaining system constraints and battery safety requirements.

---

## Overview

Modern energy systems need to balance multiple resources such as:

- Grid electricity
- Solar generation
- Battery storage
- Charging and discharging
- Energy costs
- Operational constraints

GridWise addresses this problem through a pipeline that transforms
natural-language operator instructions into structured optimization
constraints.

```text
┌─────────────────────┐
│  Operator Input     │
│  Natural Language   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   LLM Interpreter   │
│  Directive Parsing  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     Guardrails      │
│ Validation & Safety │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  CP-SAT Optimizer   │
│     OR-Tools        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 24-Hour Energy Plan │
└─────────────────────┘
