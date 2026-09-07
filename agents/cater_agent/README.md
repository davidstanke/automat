# 🥪 In-House Catering Agent (`cater_agent`)

An agentic application built using the Google Agent Development Kit (ADK) that proposes curated in-house catering menu options for team lunch meetings.

The agent is exposed via the open **Agent-to-Agent (A2A)** protocol, allowing the central `luncher_agent` orchestrator to call, delegate, and collaborate with it.

---

## 🏛️ Architecture & Mock Menus

The Catering Agent proposes 3 curated in-house catering menus:
1. **Menu 1 (Buffalo Chicken Wrap Platter)**: buffalo chicken wrap, mixed greens salad, chocolate cookie, assorted sodas
2. **Menu 2 (Veggie Taco Fiesta)**: veggie tacos, snow pea salad, apple tartlets, tea service
3. **Menu 3 (Indian Curry Feast)**: lamb vindaloo, spiced cauliflower, naan, orange-mint spa water

For the initial version, `cater_agent` returns static mock menu suggestions without performing external database or inventory retrieval.

---

## 🛠️ Configuration

The agent runs on port 8083 by default:
```bash
uv --directory agents/cater_agent run main.py
```

---

## 🛰️ A2A Integration

When running, the agent automatically advertises its capabilities via an **Agent Card** at:
```
http://localhost:8083/a2a/app/.well-known/agent-card.json
```
