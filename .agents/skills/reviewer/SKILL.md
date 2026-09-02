---
name: reviewer
description: >-
  Automated SDLC Pull Request Reviewer Agent skill. Use when the user asks to "review PR",
  "run code review", "review pull request", or inspect code changes for clean code and maintainability.
  Automatically evaluates code changes with a multi-reviewer council (Clean Code, Maintainability,
  and Defect Inspection) and posts structured reviews with line comments.
---

# Pull Request Reviewer Agent Skill

This skill provides the standard workflow to invoke the **Reviewer Agent** (`sdlc-agents/reviewer`), evaluating pull requests for clean code, structural maintainability, and runtime defect safety.

---

## When to Use This Skill

Activate this skill when:
- The user asks to review a Pull Request (e.g. `PR #1`).
- The user asks to perform an automated code quality or maintainability review on modified code.
- Continuous integration workflows evaluate incoming pull requests on GitHub.

---

## Agent Architecture & Subagents

```mermaid
flowchart TD
    PR["Pull Request / Branch Diff"] --> Fetch["fetch_pr (Clone & Filter Lockfiles)"]
    Fetch --> Council["Reviewer Council"]
    
    subgraph Council ["Multi-Reviewer Council"]
        CC["clean_code (Readability & Simplicity)"]
        MA["maintainability (Architecture & Types)"]
        DI["defect_inspector (Bugs & Safety)"]
    end
    
    Council --> Synth["synthesis (Scorecard & JSON Comments)"]
    Synth --> Pub["publish_review (GitHub PR Review)"]
```

---

## Invocation

### Via CLI Client:
```bash
sdlc-agents/.venv/bin/python sdlc-agents/reviewer/client.py --pr <PR_NUMBER> --repo-url <REPO_URL> --github-token <GITHUB_TOKEN>
```
