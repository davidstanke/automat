import asyncio

import pytest

from app import bookings
from app.tools import (
    get_team_members,
    book_meeting,
    get_bookings,
    find_available_slots,
)


@pytest.fixture(autouse=True)
def _isolate_local_bookings(monkeypatch: pytest.MonkeyPatch):
    """Runs each test against an empty in-process store, never Memory Bank."""
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setattr(bookings, "_local_bookings", [])


def test_get_team_members() -> None:
    members = get_team_members()
    assert isinstance(members, list)
    assert len(members) == 8
    names = [m["name"] for m in members]
    assert "Liam" in names
    assert "Maya" in names

    # Ensure dietary restrictions and cuisine preferences are stripped
    for member in members:
        assert "dietary_restrictions" not in member
        assert "cuisine_preferences" not in member
        assert "timezone" in member
        assert "weekly_availability" in member


def test_book_meeting() -> None:
    res = asyncio.run(book_meeting("Monday 10:00-11:00 AM", "Test booking"))
    assert "Successfully booked!" in res
    assert "bk_" in res
    assert "Buffalo Chicken Wrap" in res


def test_book_meeting_explicit_menu() -> None:
    res = asyncio.run(
        book_meeting(
            "Tuesday 12:00-13:00",
            "Taco Tuesday",
            catering_menu="menu_2",
        )
    )
    assert "Successfully booked!" in res
    assert "bk_" in res
    assert "Veggie Tacos" in res


def test_book_meeting_invalid_menu_rejected() -> None:
    res = asyncio.run(
        book_meeting(
            "Tuesday 12:00-13:00",
            "Invalid booking",
            catering_menu="Menu 4",
        )
    )
    assert "Error:" in res
    assert "not a valid catering menu option" in res
    assert len(bookings._local_bookings) == 0


def test_get_bookings_empty() -> None:
    assert "No meetings are currently booked." in asyncio.run(get_bookings())


def test_get_bookings_lists_what_was_booked() -> None:
    asyncio.run(book_meeting("Friday 12:00-13:00", "Team lunch"))
    listed = asyncio.run(get_bookings())
    assert "Friday 12:00-13:00" in listed
    assert "Team lunch" in listed


def test_find_available_slots_friday() -> None:
    result = asyncio.run(find_available_slots("Friday"))
    assert "## Team Roster" in result
    assert "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in result
    assert "## Available Time Slots" in result
    assert "Friday 12:00-13:00 (8 of 8 free)" in result


def test_find_available_slots_excludes_booked() -> None:
    asyncio.run(book_meeting("Friday 12:00-13:00", "Existing lunch"))
    result = asyncio.run(find_available_slots("Friday"))
    # Friday 12:00-13:00 should not be listed as an available slot
    assert "Friday 12:00-13:00 (8 of 8 free)" not in result


def test_find_available_slots_tuesday() -> None:
    result = asyncio.run(find_available_slots("Tuesday"))
    assert "## Team Roster" in result
    assert "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in result
    assert "Tuesday 13:00-14:00 (7 of 8 free - Kai unavailable)" in result

