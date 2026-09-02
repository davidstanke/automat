# BDD Acceptance Criteria & Schema Templates

This guide provides concrete templates for Behavior-Driven Development (BDD) scenarios, API contracts, and schema definitions required for agent-executable specifications.

---

## 1. BDD Acceptance Criteria Formatting

Every acceptance criterion must use standard **Given / When / Then** formatting with explicit, machine-testable assertions.

### Template: Happy Path Scenario
```markdown
* **AC1: [Successful Operation Title]**
  * **Given** [Initial system state, seeded database entities, or valid auth tokens]
  * **When** [Specific method call, HTTP request, or user action triggered]
  * **Then** [Exact expected return code, response body schema, or database mutation]
  * **And** [Any side effects, e.g., cache invalidation or telemetry emission]
```

### Template: Error & Boundary Scenario
```markdown
* **AC2: [Error or Validation Failure Scenario]**
  * **Given** [Precondition with missing required field, expired credentials, or rate limit exceeded]
  * **When** [Operation triggered with invalid parameters]
  * **Then** [Expected HTTP status (e.g., 400 Bad Request, 401 Unauthorized), error code, and error message payload]
  * **And** [Database state remains unchanged (no partial writes)]
```

---

## 2. API Contract Specification Template

When specifying REST or RPC endpoints, specify exact signatures:

```markdown
### API Endpoint Contract: `POST /api/v1/dietary-preferences`

* **Request Headers:**
  * `Authorization: Bearer <jwt_token>`
  * `Content-Type: application/json`

* **Request Body Schema:**
```json
{
  "user_id": "usr_12345",
  "allergens": ["peanuts", "dairy"],
  "dietary_restrictions": ["vegetarian"],
  "strictness_level": "strict"
}
```

* **Response Body (200 OK):**
```json
{
  "status": "success",
  "preference_id": "pref_98765",
  "updated_at": "2026-08-25T17:30:00Z"
}
```

* **Error Responses:**
  * `400 Bad Request`: `{"error": "INVALID_ALLERGEN", "message": "Unknown allergen type 'xyz'"}`
  * `401 Unauthorized`: `{"error": "AUTH_REQUIRED", "message": "Missing or expired Bearer token"}`
```

---

## 3. Machine Verification Command Standards

Each spec must include unambiguous verification commands runnable directly in the local development environment:

```markdown
## 5. Machine Verification Protocol & Definition of Done

The code execution agent must execute and pass the following commands before completing:
* [ ] **Linter / Static Analysis:** `uv run ruff check .` or `agents-cli lint`
* [ ] **Unit Tests:** `uv run pytest tests/unit/test_dietary_filter.py -v`
* [ ] **Integration Tests:** `uv run pytest tests/integration/test_dietary_e2e.py`
* [ ] **Type Checking:** `uv run mypy agents/luncher_agent/app/`
```
