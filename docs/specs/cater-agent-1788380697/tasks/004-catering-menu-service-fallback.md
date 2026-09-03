# Task [004]: Catering Menu Data Access & Offline Fallback Service

## 1. Problem to Solve
The Catering Agent must retrieve menu items from BigQuery via the BigQuery MCP server in production, but must operate with zero developer disruption when offline or in unauthenticated local environments. It must enforce a 5-second socket timeout on MCP queries and gracefully fall back to querying the local catering dataset (`data/catering/catering_menu.json`). In addition, it must filter out items that contain allergens or violate active dietary restrictions (e.g., vegan, gluten-free, dairy, peanuts).

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/cater_agent/app/menu_service.py`
  - `agents/cater_agent/tests/unit/test_menu_service.py`
- **Interfaces / Data Contracts**:
  - `CateringItem`: dictionary containing `id`, `name`, `description`, `category` ("mains", "sides", "beverages", "desserts"), `ingredients` (list of str), `allergens` (list of str), `dietary_labels` (list of str), and `price`.
  - Functions:
    - `async def query_menu_items(categories: list[str] | None = None) -> list[dict[str, Any]]`: Queries items via BigQuery MCP or falls back to local JSON dataset.
    - `def filter_items_by_preferences(items: list[dict[str, Any]], preferences: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]`: Filters out conflicting items and returns `(safe_items, applied_accommodations)`.
    - `def group_items_by_category(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]`: Returns items grouped by course category.
  - Timeout: 5-second socket timeout on MCP tool execution.
- **Non-Goals / Out-of-Scope**:
  - Do not author LLM agent prompts or tool wrappers in this task (handled in Task 005).
  - Do not modify `data/catering/catering_menu.json`.

## 3. Acceptance Criteria
- [ ] Attempts to query BigQuery MCP `catering.menu_items` when configured, with a 5.0 second timeout limit.
- [ ] Automatically detects MCP connection errors, timeouts, or unauthenticated environments and falls back to loading and querying `data/catering/catering_menu.json` without raising an unhandled exception.
- [ ] Correctly identifies and filters out dishes where `allergens` or `ingredients` match allergy constraints (e.g., "peanuts", "shellfish", "dairy").
- [ ] Correctly filters or matches `dietary_labels` for restrictions (e.g., "vegan", "vegetarian", "gluten-free").
- [ ] Returns categorized items: `mains`, `sides`, `beverages`, and `desserts`.
- [ ] Produces a human-readable list of active accommodation summaries (e.g., `["Peanut allergy (Alice)", "Vegetarian (Bob)"]`).

## 4. Verification Command
`uv --directory agents/cater_agent run pytest tests/unit/test_menu_service.py`
