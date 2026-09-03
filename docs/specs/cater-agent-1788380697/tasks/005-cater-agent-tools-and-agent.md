# Task [005]: Cater Agent ADK Agent Definition & Thematic Menu Tools

## 1. Problem to Solve
The Catering Agent must expose ADK tools and an Agent definition that proposes exactly 3 distinct, curated thematic catering menus for team lunches. Each proposed menu must strictly conform to the 4-course structure: 1–3 main dishes, 2–3 sides, at least 1 beverage, and at least 1 dessert, organized under a clear culinary theme. The agent must automatically retrieve stored dietary preferences, filter menu items, and present dietary accommodation notes. It must also expose a tool to record dietary preferences directly.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/cater_agent/app/tools.py`
  - `agents/cater_agent/app/agent.py`
  - `agents/cater_agent/tests/unit/test_cater_agent.py`
- **Interfaces / Data Contracts**:
  - `ThematicMenu` Schema (Section 4.2 of specification):
    - `menu_id`: string
    - `theme_name`: string
    - `mains`: list of objects (`name`, `description`, `allergens`, `dietary_labels`), min 1, max 3
    - `sides`: list of objects (`name`), min 2, max 3
    - `beverages`: list of objects (`name`), min 1
    - `desserts`: list of objects (`name`), min 1
  - Tools in `agents/cater_agent/app/tools.py`:
    - `async def record_dietary_preference(person_name: str, preference_type: str, details: str) -> str`
    - `async def get_dietary_preferences() -> str`
    - `async def get_thematic_menus() -> str`: Calls memory retrieval, queries safe items via `menu_service`, and formats or returns 3 thematic menus.
  - Agent in `agents/cater_agent/app/agent.py`:
    - `root_agent`: ADK `Agent` named `cater_agent` (or `catering_agent`) with Gemini model and instructions detailing 4-course menu composition and dietary safety.
    - `app`: ADK `App(name="cater_agent", root_agent=root_agent)`.
- **Non-Goals / Out-of-Scope**:
  - Do not implement orchestrator intent routing in `luncher_agent` (handled in Task 006).
  - Do not implement final multi-agent markdown proposal synthesis (handled in Task 007).

## 3. Acceptance Criteria
- [ ] `record_dietary_preference` tool persists preference to memory and returns a formatted confirmation: `"Saved dietary preference for {person_name}: {details} {preference_type}. This will be applied to all future lunch recommendations."`
- [ ] `get_thematic_menus` tool retrieves active preferences from `dietary_preferences` module, queries items through `menu_service`, and structures exactly 3 themed menus.
- [ ] Each generated menu complies with: 1 to 3 mains, 2 to 3 sides, >= 1 beverage, >= 1 dessert.
- [ ] Active dietary accommodations are summarized and included in the output (e.g., `"Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)"`).
- [ ] Unit tests verify that `record_dietary_preference` and `get_thematic_menus` conform to data contracts and produce valid 4-course menus.

## 4. Verification Command
`uv --directory agents/cater_agent run pytest tests/unit/test_cater_agent.py`
