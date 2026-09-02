# Multi-Agent Spec Council & Planning Rules

These rules apply when authoring, reviewing, or breaking down technical specifications in this workspace:

1. **6-Pillar Spec Compliance**:
   - Every specification must satisfy the 6 Pillars: File & Symbol Anchoring, BDD Given/When/Then Acceptance Criteria, Explicit Scope Boundaries, Deterministic Verification Protocols, Schema Contracts, and Granular Decomposability.
   - Never generate abstract specifications that lack real file paths and verification commands.

2. **Codebase Grounding Before Spec Drafting**:
   - The Lead Author (`spec-dra`) must inspect existing repository files, classes, models, and test fixtures before drafting or revising a specification.

3. **Council Review & Consensus**:
   - Product, Technical Architect, and Security reviews must be conducted independently and in parallel.
   - Council Chair must synthesize feedback into prioritized directives and compute consensus pass/fail gating.
   - If consensus is not reached by Round 2, Council Chair forces approval for task decomposition and writes a formal `TECHNICAL_DEBT.md` registry with assigned owners and remediation criteria.

4. **Atomic Task Decomposition (DAG) & Deterministic Linting**:
   - Tasks must touch no more than 1–3 files each.
   - Dependencies must form a strict Directed Acyclic Graph (DAG) with zero circular dependencies.
   - Every BDD scenario in the parent specification must be covered by at least one task's acceptance criteria.
   - The task breakdown manifest must pass the deterministic validator script (`validate_manifest.py`) ensuring acyclicity, atomicity, and parallel file mutex before certification.

5. **Concurrency Safety & Workspace Isolation**:
   - Parallel tasks in the DAG must touch mutually exclusive (disjoint) sets of files to eliminate write-lock collisions.
   - Parallel code-modifying workers must be spawned with `Workspace: "share"` (isolated git worktrees).
   - Agent synchronization leverages Antigravity's native in-memory completion payloads and direct reactive messaging (`send_message`).
