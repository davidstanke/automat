# Task [002]: Cater Agent Foundation & Service Scaffolding

## 1. Problem to Solve
The Luncher multi-agent architecture requires an independent, dedicated Catering Agent (`cater_agent`) running on port 8083 locally (and deployed via Agent Runtime with Agent Identity). Currently, only `luncher_agent`, `sched_agent`, and `strat_agent` exist in the `agents/` directory. A new agent package `agents/cater_agent` must be created following the standard ADK 2.0 FastAPI and A2A service pattern used across the repository.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/cater_agent/pyproject.toml`
  - `agents/cater_agent/Dockerfile`
  - `agents/cater_agent/.dockerignore`
  - `agents/cater_agent/.gitignore`
  - `agents/cater_agent/main.py`
  - `agents/cater_agent/app/__init__.py`
  - `agents/cater_agent/app/fast_api_app.py`
  - `agents/cater_agent/app/app_utils/services.py`
  - `agents/cater_agent/app/app_utils/telemetry.py`
  - `agents/cater_agent/app/app_utils/typing.py`
  - `agents/cater_agent/app/app_utils/a2a.py`
  - `agents/cater_agent/app/app_utils/reasoning_engine_adapter.py`
  - `agents/cater_agent/app/app_utils/genai_transport.py`
  - `agents/cater_agent/tests/unit/test_scaffolding.py`
- **Interfaces / Data Contracts**:
  - Service port: `8083` default (configured via `PORT` environment variable).
  - FastAPI app entrypoint: `app.fast_api_app:app`.
  - A2A Agent Card endpoint: `http://localhost:8083/a2a/app/.well-known/agent-card.json`.
  - Python package requirements in `pyproject.toml`: Python >=3.12, <3.14, `google-adk[a2a,eval,gcp,otel-gcp]>=2.5.0,<3.0.0`, `mcp>=1.0.0,<2.0.0`, `bigquery-mcp>=0.1.0`, `uvicorn`, `fastapi`, `pydantic`.
- **Non-Goals / Out-of-Scope**:
  - Do not implement menu retrieval algorithms or dietary memory logic in this task (handled in Tasks 003 and 004).
  - Do not wire up orchestrator routing in `luncher_agent` in this task (handled in Task 006).

## 3. Acceptance Criteria
- [ ] `agents/cater_agent/pyproject.toml` specifies project name `cater-agent`, required dependencies, Python `>=3.12, <3.14`, and pytest configuration targeting `.`.
- [ ] `main.py` starts a Uvicorn server hosting `app.fast_api_app:app` defaulting to port `8083`.
- [ ] `app/fast_api_app.py` initializes telemetry, establishes lifespan management with `Runner`, and mounts ADK/A2A endpoints with `attach_a2a_routes`.
- [ ] Dockerfile and Dockerignore match the standardized Agent Runtime deployment container specifications.
- [ ] Unit test `test_scaffolding.py` verifies FastAPI application creation, port configuration defaults, and route mounting without external network calls.

## 4. Verification Command
`uv --directory agents/cater_agent run pytest tests/unit/test_scaffolding.py`
