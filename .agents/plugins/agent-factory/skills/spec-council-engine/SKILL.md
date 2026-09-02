---
name: spec-council-engine
description: Multi-Agent Spec-Driven Planning & Task Decomposition Engine. Enforces 6 Pillars of Agent-Executable Specs, INVEST criteria, parallel Council review (Product, Tech, Security, Chair), and dynamic swarm task breakdown.
---

# Multi-Agent Spec-Driven Planning & Task Decomposition Engine

This skill provides complete operational guidelines, quality rubrics, BDD templates, and dynamic specialist protocols for transforming raw software ideas into deterministic, agent-executable specifications and atomic task DAGs.

---

## 🏗️ The 3-Phase Lifecycle

```
┌────────────────────────────────────────────────────────────────────────┐
│                        3-Phase Spec & Task Engine                      │
├───────────────────┬──────────────────────────────┬─────────────────────┤
│ 1. Grounded Spec  │ 2. Council Review & Approval │ 3. Dynamic Swarm    │
│    Drafting (DRA) │    (Prod, Tech, Sec, Chair)  │    Task Decomp (DAG)│
└───────────────────┴──────────────────────────────┴─────────────────────┘
```

1. **Phase 1: Grounded Spec Authoring (`spec-dra`)**:
   - Researches existing repository using `view_file`, `grep_search`, `find_by_name`, and `list_dir`.
   - Clarifies ambiguous requirements early with the user using `ask_question`.
   - Identifies real file paths, models, API routes, and test suites.
   - Outputs a full specification conforming to the **6 Pillars of Agent-Executable Specs**.

2. **Phase 2: Council Agreement & Review**:
   - **Parallel Review**: `product-reviewer`, `tech-reviewer`, and `security-reviewer` evaluate the spec concurrently and return structured assessments directly in their completion payloads.
   - **Council Chair Aggregation (`council-chair`)**: Computes consensus scores (Product, Tech, Security 1–100), resolves conflicts, and outputs prioritized revision directives.
   - **Reactive Directives & Bi-directional Clarification Loop**: If scores < 80 and round < 2, Council Chair dispatches revision directives directly to DRA via `send_message`. The DRA can query specific reviewers or the Chair via `send_message` if any critique point is ambiguous or contradictory before applying revisions.
   - **Max-Rounds Gating & Technical Debt Registry**: If round >= 2 and consensus threshold is not met, Council Chair forces approval for task breakdown to prevent deadlock, and generates a formal `TECHNICAL_DEBT.md` registry with assigned owners, remediation plans, and resolution acceptance criteria.

3. **Phase 3: Dynamic Swarm Task Decomposition & Execution**:
   - Analyzes certified spec's target files and requirements to detect domain subsystems (e.g., Database, API Endpoints, Frontend UI, Async Workers, QA).
   - Generates and invokes specialized domain subagents dynamically on the fly (`define_subagent` / `invoke_subagent`).
   - Validates the resulting task Directed Acyclic Graph (DAG) using `breakdown-critic` and the deterministic validation script `scripts/validate_manifest.py`, ensuring atomicity, acyclicity, parallel file disjointness (mutex), and 100% BDD coverage.
   - Downstream code execution swarms execute with `Workspace: "share"` for clean worktree isolation.

---

## 🏛️ The 6 Pillars of an Agent-Executable Spec

Specs written for AI code execution agents must be explicit, deterministic, and spatially anchored:

1. **File & Symbol Anchoring**: Every requirement must cite explicit file paths (e.g., `agents/luncher_agent/app/agent.py`), target classes, methods, schema definitions, and module imports to eliminate guesswork.
2. **Machine-Verifiable Acceptance Criteria (BDD)**: Every scenario must use Given/When/Then structure with concrete inputs, expected HTTP status codes, exact return shapes, or CLI outputs.
3. **Explicit Scope Fencing & Guardrails**: Specs must clearly outline **In-Scope** AND **Explicitly Out-of-Scope** items, as well as forbidden coding anti-patterns, to prevent scope creep.
4. **Deterministic Verification Protocol**: The spec must contain exact CLI commands required to run builds, linters, and unit/integration test suites (e.g., `uv run pytest tests/unit`).
5. **Schema & State Contracts**: Data mutations, API payloads, database migration schemas, and context state deltas must be explicitly declared with expected data types.
6. **Granular Decomposability**: Scope must be constrained so that tasks can be executed autonomously within a single agent execution turn (1–3 files modified max per task).

---

## 📊 The Adapted INVEST Framework for AI Agents

All specifications and stories must satisfy INVEST principles adapted for autonomous agent swarms:

* **I - Independent**: The story must be executable in isolation without blocking on unfinished parallel agent tasks.
* **N - Negotiable**: Captures business intent and value while leaving implementation syntax to the code execution agent within defined boundaries.
* **V - Valuable**: Delivers clear, verifiable functional value or technical capability.
* **E - Estimable / Executable**: Technical context is clear enough for an execution agent to plan exact tool calls without clarifying questions.
* **S - Small**: Sized to fit comfortably within a single agent execution turn or context window (1–3 files modified max per task).
* **T - Testable**: Includes concrete, automated test verification commands.

---

## 📋 Standard Specification Layout

Every generated specification must follow this structure:

```markdown
# [FEATURE-ID]: [Short, Descriptive Summary]

**Issue Type:** User Story / Feature Spec
**Status:** Ready for Development
**Priority:** [High / Medium / Low]

## 1. Description & Context
**As a** [Persona / Role],
**I want to** [Action / Feature / Goal],
**So that** [Benefit / Value / Reason].

### Codebase Anchors & Target Files
* **Files to Create / Modify:**
  * `path/to/target_file.py`
* **Reference Files & Dependencies:**
  * `path/to/reference_file.py`
* **Target Tools & Runtimes:**
  * e.g., Python 3.11+, `uv run pytest`, `ruff check .`

## 2. Business Context & Technical Background
[Concise explanation of architecture and existing patterns]

## 3. Behavior-Driven Development (BDD) Acceptance Criteria
* **AC1: [Scenario Title - Happy Path]**
  * **Given** [explicit initial state or database setup]
  * **When** [action, trigger, or API call]
  * **Then** [expected state delta, HTTP response code, or payload]
* **AC2: [Scenario Title - Error / Edge Case]**
  * **Given** [precondition with invalid input or missing authorization]
  * **When** [action or trigger]
  * **Then** [expected error code, exception, or fallback behavior]

## 4. Technical Constraints, Boundaries & Out of Scope
* **Constraints & NFRs:** [Performance metrics (p95 latency), security/auth scope, rate limits]
* **In-Scope:** [Explicit list of components and behaviors to deliver]
* **Out of Scope:** [Explicit non-goals to prevent scope creep]
* **Forbidden Patterns:** [e.g., Do NOT add third-party dependencies, do NOT modify shared DB schema]

## 5. Machine Verification Protocol & Definition of Done
The code execution agent must execute and pass the following commands before completing:
* [ ] **Build / Lint Check:** `uv run ruff check .`
* [ ] **Unit Tests:** `uv run pytest tests/unit`
* [ ] **Acceptance Criteria Verification:** All BDD Given/When/Then scenarios verified via automated tests.
* [ ] **Documentation:** Inline docstrings and API docs updated.
```

---

## 📚 Reference Subdocuments & Tooling

* **[BDD & Schema Templates](references/bdd_templates.md)**: Detailed BDD Given/When/Then syntax, REST/GraphQL contracts, and state transition matrices.
* **[Breakdown Critic Rubric](references/critic_rubric.md)**: DAG validation rules, cycle detection, task sizing limits, parallel file mutex, and acceptance criteria checklists.
* **[Dynamic Specialist Guide](references/dynamic_specialist_guide.md)**: Protocols for analyzing specs, synthesizing dynamic domain specialist prompts, and orchestrating parallel task creation.
* **[Manifest & DAG Validator CLI](scripts/validate_manifest.py)**: Deterministic Python script for programmatic validation of DAG acyclicity, task atomicity, parallel file mutex, and BDD coverage.
