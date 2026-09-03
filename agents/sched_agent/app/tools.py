import os
import json

from . import bookings

# Resolve DATA_DIR cleanly for local, container, or package execution
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.getenv("DATA_DIR", os.path.join(_CURRENT_DIR, "data"))

MEMBERS_FILE = os.path.join(DATA_DIR, "team_members.json")


def get_team_members() -> list[dict]:
    """Loads and returns the team members' profiles and weekly availability schedules.

    This lists each member's timezone and weekly availability slots.
    """
    print("[Scheduling Agent] Fetching team members profiles...")
    try:
        if os.path.exists(MEMBERS_FILE):
            with open(MEMBERS_FILE, "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"[Scheduling Agent] Error reading {MEMBERS_FILE}: {e}")
        return []


async def book_meeting(time_slot: str, reason: str = "") -> str:
    """Records a confirmed meeting in the shared team bookings.

    Args:
        time_slot: The day and time range of the confirmed meeting, e.g., "Monday 10:00-11:00".
        reason: Optional brief reason/summary for selecting this choice.
    """
    print(f"[Scheduling Agent] Finalizing booking: {time_slot}...")
    try:
        booking = await bookings.add_booking(time_slot, reason)
        return (
            f"Successfully booked! Meeting scheduled for {time_slot}. "
            f"Booking ID: {booking['booking_id']}."
        )
    except Exception as e:
        return f"Failed to book meeting: {str(e)}"


async def get_bookings() -> str:
    """Lists every meeting already booked by the team, oldest first.

    Bookings are shared across the whole team, so this returns the same list
    regardless of who asks. Use it to avoid double-booking a slot.
    """
    print("[Scheduling Agent] Fetching existing team bookings...")
    try:
        existing = await bookings.list_bookings()
        if not existing:
            return "No meetings are currently booked."
        lines = [
            f"- {b['time_slot']}"
            + (f" ({b['reason']})" if b.get("reason") else "")
            + f" (booking {b['booking_id']})"
            for b in existing
        ]
        return "Existing team bookings:\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to read bookings: {str(e)}"


async def cancel_booking(booking_id: str) -> str:
    """Cancels a booked meeting, freeing its time slot for the whole team.

    Args:
        booking_id: Id of the booking to cancel, as shown by `get_bookings`,
            e.g. "bk_1786830033". Call `get_bookings` first if the user named a
            day rather than an id -- cancelling the wrong meeting is not undoable.
    """
    print(f"[Scheduling Agent] Cancelling booking {booking_id}...")
    try:
        if await bookings.delete_booking(booking_id):
            return f"Cancelled booking {booking_id}. Its time slot is free again."
        return f"No booking {booking_id} exists. Call get_bookings for the current list."
    except Exception as e:
        return f"Failed to cancel booking: {str(e)}"


async def cancel_all_bookings(expected_count: int) -> str:
    """Cancels every booking the team has, clearing the shared calendar.

    This affects everyone, not just the person asking, and cannot be undone. Call
    `get_bookings` immediately before, tell the user how many will go, and only
    proceed once they confirm.

    Args:
        expected_count: How many bookings `get_bookings` just returned. The
            cancellation is refused if the collection no longer holds exactly
            that many, which catches a stale count and a guessed one alike.
    """
    print(f"[Scheduling Agent] Clearing all bookings (expecting {expected_count})...")
    try:
        deleted = await bookings.delete_all_bookings(expected_count)
        if deleted < 0:
            return (
                f"Refused: the team does not have exactly {expected_count} bookings. "
                "Call get_bookings again and retry with the number it reports."
            )
        if deleted == 0:
            return "There were no bookings to cancel."
        return f"Cancelled all {deleted} bookings. Every slot is free again."
    except Exception as e:
        return f"Failed to cancel bookings: {str(e)}"


def _parse_time_to_minutes(time_str: str) -> int:
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def _match_day_of_week(text: str) -> str | None:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    t = text.lower()
    for d in days:
        if d.lower() in t:
            return d
    return None


async def find_available_slots(day_of_week: str = "Friday", duration_minutes: int = 60) -> str:
    """Calculates and ranks overlapping team availability for a specific day of the week.

    Fast deterministic interval tool (<1ms) that cross-references all team members'
    weekly availability schedules and existing bookings to generate a verified shortlist
    with exact attendance counts per slot.

    Args:
        day_of_week: The target day (e.g. 'Friday', 'Tuesday', 'Monday'). Defaults to 'Friday'.
        duration_minutes: The slot duration in minutes (default 60).
    """
    print(f"[Scheduling Agent] Finding available slots for {day_of_week}...")
    target_day = _match_day_of_week(day_of_week) or "Friday"
    members = get_team_members()
    if not members:
        return "No team members found."

    member_names = [m["name"] for m in members]
    total_members = len(members)
    roster_line = f"Team ({total_members}): {', '.join(member_names)}"

    # Fetch existing bookings to avoid proposing double-booked slots
    existing_bookings = []
    try:
        existing_bookings = await bookings.list_bookings()
    except Exception as e:
        print(f"[Scheduling Agent] Could not check bookings: {e}")

    booked_slots = set()
    for b in existing_bookings:
        ts = b.get("time_slot", "").lower()
        if target_day.lower() in ts:
            booked_slots.add(ts)

    # Standard candidate start hours (prioritize lunch window 11:00-14:00, then full day)
    candidate_start_hours = [12, 13, 11, 10, 14, 9, 15, 16]
    evaluated_slots = []

    for start_h in candidate_start_hours:
        s_min = start_h * 60
        e_min = s_min + duration_minutes
        end_h = start_h + (duration_minutes // 60)
        end_m = duration_minutes % 60
        slot_label = f"{target_day} {start_h:02d}:00-{end_h:02d}:{end_m:02d}"

        # Check if slot conflicts with an existing booking
        is_booked = any(
            f"{start_h:02d}:00" in bs or f"{start_h}:{0:02d}" in bs
            for bs in booked_slots
        )

        free_members = []
        unavailable_members = []

        for m in members:
            day_slots = m.get("weekly_availability", {}).get(target_day, [])
            is_free = False
            for slot in day_slots:
                try:
                    sh, eh = slot.split("-")
                    if _parse_time_to_minutes(sh) <= s_min and _parse_time_to_minutes(eh) >= e_min:
                        is_free = True
                        break
                except Exception:
                    continue
            if is_free:
                free_members.append(m["name"])
            else:
                unavailable_members.append(m["name"])

        free_count = len(free_members)
        evaluated_slots.append({
            "slot_label": slot_label,
            "free_count": free_count,
            "free_members": free_members,
            "unavailable": unavailable_members,
            "is_booked": is_booked,
            "is_lunch_hour": 11 <= start_h <= 13,
        })

    # Sort slots: unbooked first, then highest free_count, then lunch hours
    evaluated_slots.sort(
        key=lambda s: (not s["is_booked"], s["free_count"], s["is_lunch_hour"]),
        reverse=True,
    )

    viable_slots = [s for s in evaluated_slots if not s["is_booked"] and s["free_count"] > 0][:4]

    output_lines = [
        "## Team Roster",
        roster_line,
        "",
        "## Available Time Slots",
    ]

    if not viable_slots:
        output_lines.append(f"No unbooked slots are available for the entire team on {target_day}.")
        if booked_slots:
            output_lines.append(f"(Existing bookings: {', '.join(booked_slots)})")
    else:
        for idx, s in enumerate(viable_slots, 1):
            fc = s["free_count"]
            if fc == total_members:
                unavail_str = f"{fc} of {total_members} free"
            else:
                unavail_names = ", ".join(s["unavailable"])
                unavail_str = f"{fc} of {total_members} free - {unavail_names} unavailable"
            output_lines.append(f"{idx}. {s['slot_label']} ({unavail_str})")

    return "\n".join(output_lines)
