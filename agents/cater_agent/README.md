# 🍱 Catering Agent

An agentic service built using the Google Agent Development Kit (ADK) that coordinates lunch catering orders, menu retrieval, and dietary preference alignment.

It is exposed via the **Agent-to-Agent (A2A)** protocol, making it ready for multi-agent collaboration and fully compatible with Google's managed **Agent Runtime**.

---

## 🚀 Local Development & Execution

Run from the repository root:

```bash
uv --directory agents/cater_agent run main.py
```

The server boots and listens on `0.0.0.0:8083` (configurable via `PORT`).

Retrieve its **Agent Card** at:

```
http://localhost:8083/a2a/app/.well-known/agent-card.json
```
