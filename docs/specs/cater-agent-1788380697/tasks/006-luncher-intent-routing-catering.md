# Task [006]: Luncher Agent Sub-Agent Discovery & Intent Routing for Dietary Preferences

## 1. Problem to Solve
The Luncher Orchestrator (`luncher_agent`) currently only routes between `"plan"` (which queries `strategy_agent` and `scheduling_agent`) and `"book"` (which delegates to `scheduling_agent`). It does not discover `catering_agent`, nor does it handle dietary preference updates. In accordance with Section 3 and BDD Scenarios 2 & 3:
1. Prompts that solely state dietary preferences (e.g., *"Carol is vegetarian and Dan cannot eat dairy"*) must be routed directly to memory persistence via `catering_agent`, returning a confirmation and future planning invitation without triggering booking or time slot generation.
2. Prompts combining preferences with planning (e.g., *"Schedule lunch for Friday, and note that Eve is gluten-free"*) must persist the preference first, then proceed to parallel data gathering across strategy, scheduling, and catering.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/luncher_agent/app/agent.py`
  - `agents/luncher_agent/tests/unit/test_intent_router.py`
- **Interfaces / Data Contracts**:
  - `catering_agent`: instantiated via `discover_sub_agent(agent_name="catering_agent", default_local_url="http://localhost:8083/a2a/app/.well-known/agent-card.json", ...)` with a 10.0-second timeout.
  - `IntentClassification`:
    ```python
    class IntentClassification(BaseModel):
        intent: Literal["plan", "book", "dietary_preference", "plan_with_preference"]
        preference_updates: list[dict[str, str]] = []
    ```
  - Dedicated preference confirmation format:
    `"Saved dietary preference for {person}: {details} ({type}). This will be applied to all future lunch recommendations.\n\nWould you like to plan a team lunch now?"`
  - Workflow graph updates:
    - `"plan"` route executes `(strategy_agent, scheduling_agent, catering_agent)` in parallel.
    - `"dietary_preference"` node invokes `catering_agent` memory update and terminates with confirmation.
    - `"plan_with_preference"` persists preference and runs planning pipeline.
- **Non-Goals / Out-of-Scope**:
  - Do not modify markdown proposal formatting (handled in Task 007).
  - Do not modify booking persistence logic in `sched_agent` (handled in Task 001).

## 3. Acceptance Criteria
- [ ] `catering_agent` is discovered using existing `discover_sub_agent` logic with local default `http://localhost:8083/a2a/app/.well-known/agent-card.json` and a 10-second timeout.
- [ ] Prompts stating only dietary constraints (e.g., *"Alice is allergic to shellfish and peanuts"*) classify as preference update and route to dietary persistence without triggering `scheduling_agent` or booking.
- [ ] Prompts combining planning and dietary preference classify as combined intent, saving the preference before/during the proposal generation.
- [ ] Standard planning prompts (e.g., *"Plan lunch for the launch team next Tuesday"*) trigger parallel queries to `strategy_agent`, `scheduling_agent`, and `catering_agent`.
- [ ] Unit tests in `test_intent_router.py` verify accurate classification and event routing for all 4 intent scenarios.

## 4. Verification Command
`uv --directory agents/luncher_agent run pytest tests/unit/test_intent_router.py`
