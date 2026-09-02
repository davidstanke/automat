---
name: spec-council-engine
description: Multi-Agent Spec-Driven Authoring & Review Engine. Enforces specification quality standards, INVEST criteria, and parallel Reviewer evaluation (Product, Tech, Security) to produce certified specifications.
---

# Multi-Agent Spec-Driven Authoring & Review Engine

This skill provides operational guidelines, quality rubrics, and BDD templates for transforming software concepts into clear, deterministic, and certified product specifications. Its sole responsibility is delivering a certified specification document—it does not specify or perform code implementation.

---

## 🏗️ The 6-Step Spec Lifecycle

```
┌────────────────────────────────────────────────────────────────────────┐
│                   6-Step Spec Authoring & Review Flow                  │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Proactive Discovery (DRA interviews user on key choices via Q&A)   │
│ 2. Feature Branch Checkout (`feature/<feature-slug>-<timestamp>`)      │
│ 3. Write Specification File to Disk (`docs/specs/...`)                 │
│ 4. Invoke Reviewers (`product`, `tech`, `security` reviewers)          │
│ 5. Revise Specification (DRA consults user on trade-offs & updates)    │
│ 6. Finish & Deliver with Confirmation (Summarize choices & get verify) │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Step 1: Proactive Discovery & Clarification (`spec-dra`)**:
   - Always conducts an initial discovery probing interview via `ask_question` (2–4 targeted questions on UX workflows, edge-case handling, scope boundaries, and persistence/storage trade-offs).
   - Records resolved user preferences and choices to seed Section 2 ("Key Product Decisions & User Feedback").
   - Analyzes user personas, business value, user workflows, BDD acceptance criteria, and data contracts.
   - Focuses strictly on product requirements and behavior without code implementation details.

2. **Step 2: Feature Branch Checkout**:
   - `spec-dra` stashes any uncommitted modifications (`git stash`).
   - Checks out a new Git branch named `feature/<feature-slug>-<timestamp>` matching the feature where `<timestamp>` is the Unix epoch timestamp derived from context (`git checkout -b feature/<feature-slug>-<timestamp>`).
   - Restores stashed changes (`git stash pop`).

3. **Step 3: Write Specification to Disk**:
   - `spec-dra` writes the initial specification to `docs/specs/<feature-slug>-<timestamp>.md` using `write_to_file`.

4. **Step 4: Invoke Reviewers (Direct Top-Level Invocation)**:
   - The parent orchestrator invokes `product-reviewer`, `tech-reviewer`, and `security-reviewer` in parallel as direct subagents via `invoke_subagent` (`model: flash`). This ensures all reviewer agents appear actively in Antigravity's **Subagents** panel.
   - Reviewers inspect the specification file on disk (`docs/specs/<feature-slug>-<timestamp>.md`) and return structured assessments directly in their completion payloads (pure in-memory).

5. **Step 5: Revise Specification & Consult on Trade-Offs**:
   - `spec-dra` synthesizes feedback directly from the reviewers.
   - Proactively consults the user interactively via `ask_question` regarding any non-trivial architectural trade-offs, scope additions, or alternative solutions suggested by reviewers (as well as any critical blocker with score < 50).
   - `spec-dra` updates the specification file on disk (`docs/specs/<feature-slug>-<timestamp>.md`) with addressed feedback and embeds Section 2 ("Key Product Decisions & User Feedback") and Section 7 ("Review & Quality Scorecard").

6. **Step 6: Finish & Deliver with Confirmation**:
   - `spec-dra` verifies the final specification file and presents the certified specification link, active branch name, and key user-aligned choices to the user.
   - Explicitly invites user confirmation and feedback on any potential refinements before implementation begins.

---

## 📊 The Adapted INVEST Framework for Specs

All specifications and stories must satisfy INVEST principles:

* **I - Independent**: The story must be clearly scoped without unstated external dependencies.
* **N - Negotiable**: Captures business intent and value while leaving technical details open within defined architectural boundaries.
* **V - Valuable**: Delivers clear, verifiable functional value or technical capability.
* **E - Estimable / Feasible**: Functional context is clear enough to evaluate without ambiguity.
* **S - Small**: Sized to fit comfortably as a focused, cohesive feature scope.
* **T - Testable / Verifiable**: Acceptance criteria are concrete, measurable, and unambiguous via Given/When/Then scenarios.

---

## 📋 Standard Specification Layout

Every generated specification must follow this structure:

```markdown
# [FEATURE-ID]: [Short, Descriptive Summary]

**Issue Type:** User Story / Feature Spec
**Status:** Certified
**Priority:** [High / Medium / Low]

## 1. Description & Context
**As a** [Persona / Role],
**I want to** [Action / Feature / Goal],
**So that** [Benefit / Value / Reason].

## 2. Key Product Decisions & User Feedback
* **Decision 1:** [Clarified user choice, UX preference, or scope boundary resolved via Q&A]
* **Decision 2:** [Architectural or trade-off resolution aligned with user]

## 3. Business Context & User Workflow
[Concise explanation of business context, user workflows, and target personas]

## 4. Behavior-Driven Development (BDD) Acceptance Criteria
* **AC1: [Scenario Title - Happy Path]**
  * **Given** [explicit initial state, authenticated user, or preconditions]
  * **When** [action, event trigger, or user interaction]
  * **Then** [expected state delta, response outcome, or visible result]
* **AC2: [Scenario Title - Error / Edge Case]**
  * **Given** [precondition with invalid input or missing authorization]
  * **When** [action or trigger occurs]
  * **Then** [expected error response, message, or fallback behavior]

## 5. Constraints, Boundaries & Out of Scope
* **Non-Functional Requirements (NFRs):** [Performance metrics, latency targets, security/auth policies, rate limits]
* **In-Scope:** [Explicit list of capabilities and behaviors to deliver]
* **Out of Scope:** [Explicit non-goals to prevent scope creep]

## 6. Specification Quality Checklist
* [ ] **Requirements Clarity:** User persona, business intent, and value proposition clearly stated.
* [ ] **User Feedback Alignment:** Key product decisions and user feedback explicitly recorded in Section 2.
* [ ] **BDD Acceptance Coverage:** Given/When/Then scenarios cover happy paths, error handling, and edge cases.
* [ ] **Scope Boundaries:** In-scope and out-of-scope boundaries explicitly demarcated.
* [ ] **Data & Contract Definitions:** Request/response schemas, state changes, and types explicitly documented.
* [ ] **Storage & Threat Hygiene:** Strict value safelist validation and sandbox/incognito resilience documented for client state.
* [ ] **Accessibility & ARIA Coverage:** Dynamic announcements and keyboard navigation requirements specified.

## 7. Review & Quality Scorecard
### Consensus Scorecard
| Reviewer Role | Score (1-100) | Status | Key Focus Area |
| :--- | :--- | :--- | :--- |
| **Product Reviewer** | [Score]/100 | [Approved / Needs Revision] | INVEST, User Personas, Edge Cases |
| **Tech Reviewer** | [Score]/100 | [Approved / Needs Revision] | Feasibility, Data Contracts, NFRs |
| **Security Reviewer** | [Score]/100 | [Approved / Needs Revision] | OWASP, Auth/RBAC, Threat Hygiene |
| **Overall Verdict** | **[Average]/100** | **CERTIFIED_APPROVED** | Single-pass synthesis by spec-dra |

### Synthesis Notes & Addressed Feedback
* [Summary of improvements made during review synthesis]

### Future Scope & Deferred Items (Optional)
* **ITEM-001**: [Non-blocking improvement or future optimization deferred past V1]
```

---

## 📚 Reference Subdocuments & Tooling

* **[BDD & Schema Templates](references/bdd_templates.md)**: Detailed BDD Given/When/Then syntax, REST/GraphQL contracts, and state transition matrices.


