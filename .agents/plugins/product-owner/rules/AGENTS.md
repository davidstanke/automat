# Multi-Agent Spec Rules

These rules apply when authoring and reviewing feature specifications in this workspace:

1. **Grounded & Verifiable Specifications**:
   - Every specification must be grounded in user requirements, explicit domain models / data contracts, and unambiguous Given/When/Then acceptance criteria. Never generate abstract specifications.
   - Specifications must explicitly capture user decisions and feedback in a dedicated section ("Key Product Decisions & User Feedback").

2. **Proactive User Feedback & Continuous Alignment**:
   - The specification author (`spec-dra`) must proactively seek user feedback on critical choices rather than making unilateral assumptions.
   - Formulate clear, multiple-choice questions with recommended options using `ask_question`.

3. **Requirements Focus (No Implementation Details)**:
   - Specifications must focus strictly on product requirements, user behavior, domain boundaries, and verifiable acceptance criteria.
   - Do NOT include technical code implementation specifics, target source file paths, class/function scaffolding, or programming language implementation details.
   - For client-side state/storage features, specifications must explicitly mandate strict value safelisting, graceful sandbox/incognito fallback, and ARIA assistive announcements.

4. **6-Step Specification Lifecycle**:
   - **Step 1 (Proactive Discovery & Clarification)**: `spec-dra` conducts an initial multi-aspect probing interview via `ask_question` (2–4 targeted questions on UX flows, edge cases, scope boundaries, and persistence trade-offs), even when initial prompts appear clear.
   - **Step 2 (Branch Checkout)**: `spec-dra` checks out a new Git branch named `feature/<feature-slug>-<timestamp>` (e.g., `feature/user-auth-1756260000`, appending the current Unix epoch timestamp) matching the feature. If working tree changes exist, they are stashed before checkout and restored afterward.
   - **Step 3 (Write Spec to Disk)**: `spec-dra` writes the initial specification to `docs/specs/<feature-slug>-<timestamp>.md` including initial user choices.
   - **Step 4 (Invoke Reviewers)**: To ensure visibility in the Antigravity "Subagents" panel, the parent agent/orchestrator directly spawns the three council reviewers (`product-reviewer`, `tech-reviewer`, `security-reviewer`) using `invoke_subagent` (`model: flash`). Reviewers inspect the specification file on disk and return structured assessments directly in their completion payloads (pure in-memory).
   - **Step 5 (Revise Specification & Consult on Trade-Offs)**: `spec-dra` synthesizes feedback, consults the user interactively via `ask_question` regarding any non-trivial architectural trade-offs, scope additions, or alternative solutions suggested by reviewers (as well as any critical blocker with score < 50), updates the specification file on disk, and embeds the consensus Review Scorecard and documented user choices.
   - **Step 6 (Finish & Deliver with Confirmation)**: `spec-dra` verifies the specification, summarizes the key user-aligned choices, scorecard, and spec link, and explicitly invites user confirmation or refinements before engineering handoff.

5. **Spec-Only Scope**:
   - The sole objective of `product-owner` (including `spec-dra` and the reviewer agents) is to deliver a complete, certified specification document on its dedicated feature branch. It does not perform, manage, or reference code implementation.



