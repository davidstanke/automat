# 🛰️ Luncher Orchestrator Agent

The centralized Orchestrator Agent (the cognitive frontend) for the Luncher platform. It coordinates with both `strat_agent` (Strategy Agent) and `sched_agent` (Scheduling Agent) using the Google Agent Development Kit (ADK) and the Agent-to-Agent (A2A) protocol.

---

## 🏗️ Architecture

The Orchestrator acts as the "cognitive frontend" or user gateway, delegating specialized sub-tasks to the backend agents:
1. **`strat_agent`**: Queried via A2A to extract current corporate strategic goals (e.g., launching *OmniChef* or strategic business constraints).
2. **`sched_agent`**: Queried via A2A to perform team schedule checks and manage meeting bookings.

---

## ☁️ Deployment Target

`luncher_agent` deploys to **Agent Runtime** (`deployment_target: agent_runtime`). It coordinates
with sub-agents over the A2A protocol and serves reasoning engine routes, A2A endpoints, and the
agent card. See the root `README.md` and `docs/deploy.md` for the deployment sequence.

---

## 🚀 Local Development & Execution

Start each agent in its own terminal, from the repository root. Every `main.py`
defaults to the port shown, so no `PORT` override is needed.

### 1. Start Strategy Agent (port 8081)
```bash
uv --directory agents/strat_agent run main.py
```

### 2. Start Scheduling Agent (port 8082)
```bash
uv --directory agents/sched_agent run main.py
```

### 3. Start Orchestrator Agent (port 8080)
```bash
uv --directory agents/luncher_agent run main.py
```

Then open the dev UI:

```
http://localhost:8080
```

then prompt the orchestrator, e.g.

```
Plan a team lunch meeting for next week that aligns with our corporate strategy.
```

The orchestrator replies with a structured Markdown lunch proposal including strategic rationale, team roster, ranked time slots with attendance counts, and a recommended option.

To book, reply directly in chat with your preferred slot (e.g., *"Book Tuesday 12:00"* or *"Option 1 works"*). The agent will book the meeting and return a confirmation with the booking details and food reminder.

> **Note:** use `main.py`, not `adk web`. Both serve the same ADK dev UI, but `adk web`
> builds its own app via the ADK CLI and therefore skips `app/fast_api_app.py` — so the
> A2A endpoints, the agent card and `/feedback` would not be served.
