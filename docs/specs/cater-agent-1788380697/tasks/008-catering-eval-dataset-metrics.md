# Task [008]: Automated Evaluation Dataset & Catering Grading Suite

## 1. Problem to Solve
The specification requires automated evaluation via `agents-cli eval generate` and `agents-cli eval grade` against a dedicated catering evaluation dataset (`tests/eval/datasets/catering-dataset.json`) and grading criteria in `eval_config.yaml`. The evaluation suite must measure `final_response_quality`, `hallucination`, and `dietary_filtering` across the five core BDD acceptance scenarios (proposing 3 thematic menus, filtering by active preferences, updating preferences without booking, booking with catering details, and offline fallback).

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/luncher_agent/tests/eval/datasets/catering-dataset.json`
  - `agents/luncher_agent/tests/eval/catering_eval.py`
  - `agents/luncher_agent/tests/eval/eval_config.yaml`
  - `agents/luncher_agent/tests/unit/test_eval_config.py`
- **Interfaces / Data Contracts**:
  - `catering-dataset.json`: Array of ADK eval instances containing `input`, `expected_output_patterns`, and `context`:
    - Scenario 1: Standard lunch request expecting 3 thematic menus with 4 courses each.
    - Scenario 2: Active allergies (peanuts, shellfish, vegetarian) expecting allergen exclusion and explicit filtering notes.
    - Scenario 3: Pure dietary update expecting confirmation and no meeting proposal.
    - Scenario 4: Booking with catering selection expecting booking ID and catering summary.
  - Custom metric functions in `catering_eval.py`:
    - `dietary_filtering(instance, response) -> dict[str, float]`: Evaluates that prohibited ingredients do not appear and accommodation note is present.
    - `menu_structure_compliance(instance, response) -> dict[str, float]`: Evaluates presence of 3 menus and 4 courses per menu.
  - `eval_config.yaml`: Registers `dietary_filtering` and `menu_structure_compliance` alongside standard response quality metrics.
- **Non-Goals / Out-of-Scope**:
  - Do not automatically run integration tests or eval commands during unit test verification (strictly adhering to testing rules).
  - Do not alter core agent runtime deployment scripts.

## 3. Acceptance Criteria
- [ ] `catering-dataset.json` contains valid JSON with test instances representing all 5 specification BDD scenarios.
- [ ] Custom evaluators in `catering_eval.py` correctly calculate deterministic scores (0.0 to 1.0) for dietary exclusion, accommodation phrasing, and 4-course structure.
- [ ] `eval_config.yaml` includes the newly added catering metrics in `custom_metrics`.
- [ ] `test_eval_config.py` executes under the unit test suite and validates that `catering-dataset.json` schema is valid and custom evaluation functions accurately score passing and failing mock responses.

## 4. Verification Command
`uv --directory agents/luncher_agent run pytest tests/unit/test_eval_config.py`
