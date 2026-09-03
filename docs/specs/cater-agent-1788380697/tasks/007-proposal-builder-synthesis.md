# Task [007]: Luncher Proposal Builder & Synthesizer Catering Integration

## 1. Problem to Solve
Currently, `luncher_agent`'s `proposal_builder.py` only outputs a placeholder line: `"You might want to order some food for this meeting."` for catering. In addition, the booking turn in `ROLE_DESCRIPTION` outputs a food reminder rather than the confirmed catering menu. In accordance with BDD Scenarios 1, 2, and 4, the proposal builder and synthesizer agent must present 3 distinct thematic catering menus (mains, sides, beverage, dessert), display an explicit note of active dietary accommodations (e.g., `"Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)"`), and format booking confirmations with the selected catering menu.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/luncher_agent/app/proposal_builder.py`
  - `agents/luncher_agent/app/agent.py`
  - `agents/luncher_agent/tests/unit/test_proposal_builder.py`
- **Interfaces / Data Contracts**:
  - Update `build_lunch_proposal_markdown`:
    ```python
    def build_lunch_proposal_markdown(
        *,
        title: str,
        rationale: str,
        attendees: list[str],
        time_slots: list[dict],
        recommended_slot: str,
        catering_menus: list[dict],
        accommodations: str = "",
    ) -> str
    ```
  - Update `format_lunch_proposal` tool signature to accept catering menus and accommodation notes.
  - The formatted proposal must contain:
    - Title & Strategic Rationale
    - Included Team Members
    - Proposed Time Slots
    - Proposed Catering Menus (3 thematic menus, each with mains, sides, beverages, desserts)
    - Active accommodations note (e.g. `### Dietary Accommodations\nFiltered to accommodate: ...`)
  - Synthesizer prompt in `agents/luncher_agent/app/agent.py`:
    - Guide the model to extract and forward catering items from `catering_agent` to `format_lunch_proposal`.
    - Update booking confirmation prompt to delegate selected slot and catering menu to `scheduling_agent` and format confirmation:
      - **Time Slot**: [selected slot]
      - **Attendees**: [list of attendees]
      - **Booking ID**: [booking id]
      - **Catering Menu**: [Theme name: selected items]
- **Non-Goals / Out-of-Scope**:
  - Do not modify `sched_agent`'s internal booking storage (handled in Task 001).
  - Do not modify BigQuery retrieval queries (handled in Task 004).

## 3. Acceptance Criteria
- [ ] `build_lunch_proposal_markdown` renders a clean Markdown section for 3 thematic catering menus conforming to the 4-course contract.
- [ ] Displays active dietary accommodations prominently when constraints are present.
- [ ] Replaces the obsolete `"You might want to order some food for this meeting."` placeholder completely.
- [ ] Validates that exactly 3 thematic catering menus are provided, raising a `ValueError` if fewer or malformed menus are passed.
- [ ] `synthesizer_agent` prompt instructs the model to accurately capture chosen catering menu details during booking turns.
- [ ] Unit tests in `test_proposal_builder.py` verify markdown construction with and without dietary accommodations, and ensure schema validation errors are properly handled.

## 4. Verification Command
`uv --directory agents/luncher_agent run pytest tests/unit/test_proposal_builder.py`
