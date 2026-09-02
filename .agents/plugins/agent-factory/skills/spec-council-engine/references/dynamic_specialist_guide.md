# Dynamic Specialist Swarm Spawning Guide

This guide describes how the Phase 3 Swarm Orchestrator dynamically identifies subsystems in a certified spec, defines custom specialist subagents on the fly, and coordinates concurrent task decomposition.

---

## 1. Subsystem Detection Protocol

When the Spec Council certifies a specification, the Swarm Orchestrator parses two key sections of `SPECIFICATION.md`:
1. **Codebase Anchors & Target Files**:
   - `models/`, `db/`, `migrations/`, `schemas/` ➔ **Database & Schema Specialist**
   - `routes/`, `fast_api_app.py`, `endpoints/`, `services/` ➔ **Backend API Specialist**
   - `agent.py`, `workflows/`, `subagents/` ➔ **Agent Orchestration Specialist**
   - `ui/`, `components/`, `a2ui.py` ➔ **Frontend / A2UI Specialist**
   - `tests/`, `eval/`, `benchmarks/` ➔ **QA & Verification Specialist**
2. **Technical Constraints & NFRs**:
   - High concurrency / Redis / Caching ➔ **Performance & Caching Specialist**
   - Auth / OAuth / Crypto / RBAC ➔ **Security & Identity Specialist**

---

## 2. On-The-Fly Subagent Definition (`define_subagent`)

For each detected domain, the orchestrator invokes `define_subagent` with targeted system prompts:

```json
{
  "name": "domain-specialist-fastapi",
  "description": "On-the-fly specialist for decomposing FastAPI endpoints and request models",
  "system_prompt": "You are a Principal FastAPI Engineer. Your role is to break down the API endpoint requirements from the certified specification into atomic, 1-3 file tasks with explicit BDD Given/When/Then acceptance criteria and verification commands.",
  "enable_write_tools": false,
  "enable_subagent_tools": false,
  "enable_mcp_tools": false
}
```

---

## 3. Concurrent Swarm Invocation (`invoke_subagent`)

Once defined, the orchestrator launches all specialists concurrently in a single tool call:

* **Decomposition Phase (Read-Only)**: Use `Workspace: "inherit"` as specialists only read the spec and codebase.
* **Execution Phase (Code Modification)**: When executing the resulting tasks, always set `Workspace: "share"` to give each worker an isolated git worktree, preventing file locking, race conditions, or test interference.

```json
{
  "Subagents": [
    {
      "TypeName": "domain-specialist-db",
      "Role": "Database & Models Specialist",
      "Workspace": "inherit",
      "Prompt": "Review the certified spec at docs/specs/XYZ/SPECIFICATION.md and decompose all database schemas, models, and migrations into atomic tasks."
    },
    {
      "TypeName": "domain-specialist-fastapi",
      "Role": "FastAPI Route Specialist",
      "Workspace": "inherit",
      "Prompt": "Review the certified spec at docs/specs/XYZ/SPECIFICATION.md and decompose all endpoint routing, validation, and serialization into atomic tasks."
    },
    {
      "TypeName": "domain-specialist-qa",
      "Role": "QA & Eval Specialist",
      "Workspace": "inherit",
      "Prompt": "Review the certified spec at docs/specs/XYZ/SPECIFICATION.md and decompose all unit, integration, and compliance tests into atomic verification tasks."
    }
  ]
}
```

---

## 4. Aggregation and Critic Gate

When all specialist workers report back:
1. The Antigravity runtime automatically delivers the completion payloads directly into the Orchestrator's context (reactive wakeup without file polling).
2. The Orchestrator aggregates the returned candidate tasks into a structured draft manifest.
3. The Orchestrator invokes `breakdown-critic` to perform DAG cycle detection, enforce parallel file disjointness (mutex), ensure all BDD scenarios are covered, and write the final `TASK_MANIFEST.md`.
