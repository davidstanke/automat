# Test Execution & Maintenance Rules

These rules govern how Antigravity executes and maintains tests across this repository (`/agents/*`).

---

## 1. Automatic Test Execution: Unit Tests ONLY

- **Strict Test Directory Scope:** Whenever tests are run, Antigravity ONLY needs to find and execute tests located within `agents/` (`agents/*`). Do not search for or run tests in other directories.
- **Strict Unit Test Scope:** Antigravity MUST ONLY run unit tests (`tests/unit/`) automatically.
- **Trigger Conditions for Unit Tests:**
  - Automatically after completing code modifications or refactors to verify implementation correctness.
  - When responding to general testing or verification prompts (e.g., *"test this"*, *"verify changes"*, *"check if tests pass"*).
- **Prohibited Automatic Runs:** NEVER run integration tests (`tests/integration/`) or evaluation suites (`tests/eval/`) automatically or unprompted.
- **Explicit Target Invocation:** Never run an unqualified `pytest` or `pytest tests/` command from an agent root, as this discovers integration and eval suites. Always explicitly target `tests/unit`:
  ```bash
  uv --directory agents/<agent_name> run pytest tests/unit
  ```

---

## 2. Integration & Eval Tests: Explicit Request Required

- Integration tests (`tests/integration/`) and evaluation suites (`tests/eval/`) MUST ONLY be executed when the user provides an explicit prompt specifically requesting them (e.g., *"run the integration tests"*, *"run integration tests for luncher_agent"*, *"run evals"*).
- When explicitly requested by the user, execute them using the targeted path:
  ```bash
  uv --directory agents/<agent_name> run pytest tests/integration
  ```

---

## 3. Post-Unit Test Notification

Whenever unit tests are run automatically, Antigravity MUST provide a brief notification in its response alerting the user that integration tests were skipped and providing an example prompt to run them.

### Required Notification Format:
> **Test Notice:** Unit tests ran automatically. Integration tests were not executed. To run them, reply with:
> `Run integration tests for <agent_name>` (or `Run all integration tests`).

---

## 4. Integration Test Maintenance & Authorship

- **Active Maintenance:** Integration tests must remain fully supported, up-to-date, and aligned with codebase changes.
- **Synchronized Updates:** When modifying existing features, schemas, tools, or adding new capabilities:
  - Author and update corresponding integration tests alongside unit tests.
  - Maintain correct fixtures, mock configurations, and assertions in `tests/integration/` without executing them unless explicitly requested.
