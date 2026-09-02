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
