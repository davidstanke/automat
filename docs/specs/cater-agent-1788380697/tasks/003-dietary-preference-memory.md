# Task [003]: Cater Agent Dietary Preference Memory Management

## 1. Problem to Solve
Team members and meeting organizers need to record allergies, dietary preferences, likes, and dislikes per team member or collectively for the team. These preferences must be persisted in persistent agentic memory storage (Agent Platform Memory Bank when deployed to Agent Runtime, or local in-process memory when running locally) and scoped strictly under `{"app_name": "cater_agent", "user_id": "team"}`. Free-form dietary inputs must also be sanitized against prompt and SQL injection patterns before storage.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/cater_agent/app/dietary_preferences.py`
  - `agents/cater_agent/tests/unit/test_dietary_preferences.py`
- **Interfaces / Data Contracts**:
  - `TEAM_SCOPE = {"app_name": "cater_agent", "user_id": "team"}`
  - Prefix for stored facts: `dietary_pref:`
  - Schema:
    ```json
    {
      "person_name": "string",
      "preference_type": "allergy | restriction | dislike | like",
      "details": "string",
      "created_at": "ISO-8601 string"
    }
    ```
  - Functions:
    - `sanitize_input(val: str) -> str`
    - `async def add_preference(person_name: str, preference_type: str, details: str) -> dict[str, Any]`
    - `async def list_preferences(person_name: str | None = None) -> list[dict[str, Any]]`
    - `async def delete_preference(person_name: str, details: str) -> bool`
    - `async def clear_all_preferences(expected_count: int) -> int`
- **Non-Goals / Out-of-Scope**:
  - Do not implement menu filtering in this task (handled in Task 004).
  - Do not wire up ADK agent tools in this task (handled in Task 005).

## 3. Acceptance Criteria
- [ ] Stored memories use constant team scope `{"app_name": "cater_agent", "user_id": "team"}` so preferences are shared across the team workspace.
- [ ] Validates `preference_type` against `["allergy", "restriction", "dislike", "like"]` and normalizes inputs.
- [ ] `sanitize_input` strips harmful injection characters, SQL control statements (e.g., `DROP`, `UNION`, `SELECT`), and script tags.
- [ ] `add_preference` creates a valid record with ISO-8601 UTC `created_at` timestamp and writes verbatim with `_FACT_PREFIX` to Memory Bank (or local fallback list when `GOOGLE_CLOUD_AGENT_ENGINE_ID` is unset).
- [ ] `list_preferences` yields un-corrupted records, filtering by `person_name` if supplied, or returning all team preferences.
- [ ] Handles unparseable memory facts gracefully with a logged warning without breaking `list_preferences`.

## 4. Verification Command
`uv --directory agents/cater_agent run pytest tests/unit/test_dietary_preferences.py`
