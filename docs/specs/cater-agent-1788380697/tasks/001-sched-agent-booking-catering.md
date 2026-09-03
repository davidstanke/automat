# Task [001]: Sched Agent Unified Booking Record & Catering Persistence

## 1. Problem to Solve
When a user confirms a meeting and selects a catering menu, the selected catering menu (theme name and selected food items) must be persisted directly within the shared booking record alongside the time slot, rationale, and booking ID. Currently, `sched_agent`'s booking module (`agents/sched_agent/app/bookings.py`) and tool (`agents/sched_agent/app/tools.py`) only record `time_slot` and `reason`, omitting catering menu selections.

## 2. Technical Parameters & Scope
- **Target Files**:
  - `agents/sched_agent/app/bookings.py`
  - `agents/sched_agent/app/tools.py`
  - `agents/sched_agent/app/agent.py`
  - `agents/sched_agent/tests/unit/test_bookings.py`
  - `agents/sched_agent/tests/unit/test_tools.py`
- **Interfaces / Data Contracts**:
  - Update `_new_booking(time_slot: str, reason: str = "", catering_menu: dict[str, Any] | None = None) -> dict[str, Any]` in `agents/sched_agent/app/bookings.py`.
  - Update `add_booking(time_slot: str, reason: str = "", catering_menu: dict[str, Any] | None = None) -> dict[str, Any]` in `agents/sched_agent/app/bookings.py`.
  - Update `book_meeting(time_slot: str, reason: str = "", catering_theme: str = "", catering_items: list[str] | str = "") -> str` in `agents/sched_agent/app/tools.py`.
  - The persisted `catering_menu` object must adhere to the `BookingRecord` schema:
    ```json
    {
      "theme_name": "string",
      "selected_items": ["string"]
    }
    ```
- **Non-Goals / Out-of-Scope**:
  - Do not implement menu recommendation logic in `sched_agent`.
  - Do not alter `luncher_agent` orchestrator workflow in this task.
  - Do not alter team members availability logic.

## 3. Acceptance Criteria
- [ ] `_new_booking` creates a dictionary with `booking_id` matching `^bk_[0-9]+_[a-f0-9]{6}$`, `time_slot`, `reason`, `booked_at`, and optionally `catering_menu` if provided.
- [ ] When `catering_menu` is provided, `add_booking` stores the complete dictionary including `catering_menu: {"theme_name": "...", "selected_items": [...]}` in Memory Bank fact JSON and `_local_bookings`.
- [ ] `list_bookings` correctly retrieves and returns bookings containing `catering_menu` objects.
- [ ] `book_meeting` accepts catering arguments (theme name and item list or comma-separated string) and passes the structured `catering_menu` dict to `bookings.add_booking`.
- [ ] `sched_agent` instruction in `agents/sched_agent/app/agent.py` is updated to instruct the agent to capture chosen catering menu details when booking.
- [ ] If `catering_menu` is omitted or empty, `add_booking` maintains backwards compatibility by storing a valid booking record without a `catering_menu` key or with `catering_menu=None`.

## 4. Verification Command
`uv --directory agents/sched_agent run pytest tests/unit/test_bookings.py tests/unit/test_tools.py`
