# ⚡ GridWise

### AI-Assisted Energy Optimization Platform

> 🏆 **Hackathon Project**

GridWise is an AI-assisted energy optimization platform developed for a
hackathon challenge. The system combines **LLM-based natural language
interpretation, validation guardrails, and constraint-based optimization**
to generate a feasible 24-hour energy schedule.

The platform allows operators to provide energy-related instructions in
natural language. These instructions are converted into structured
directives, validated through guardrails, and incorporated into the energy
optimization process.

---

## 🏆 Hackathon Project

GridWise was developed as part of a **Hackathon challenge** focused on
building an intelligent energy optimization solution.

### Challenge Focus

The project focuses on solving an energy management problem involving:

- Grid electricity consumption
- Solar energy generation
- Battery storage
- Battery charging and discharging
- Energy cost optimization
- Operational constraints
- Natural-language operator instructions

### Our Approach

Instead of requiring operators to manually configure every optimization
constraint, GridWise provides a natural-language interface.

```text
Operator Instruction
        ↓
LLM Interpretation
        ↓
Structured Directive
        ↓
Guardrails Validation
        ↓
CP-SAT Optimization
        ↓
24-Hour Energy Schedule
