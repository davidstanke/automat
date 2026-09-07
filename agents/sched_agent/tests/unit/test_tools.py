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


def test_book_meeting_conversational_menu_matching() -> None:
    """AC4: Conversational menu matching for explicit and descriptive phrases."""
    # Explicit ID
    res1 = asyncio.run(book_meeting("Tuesday 12:00-13:00", catering_menu_choice="menu_2"))
    assert "Successfully booked!" in res1
    assert "Veggie Taco Fiesta" in res1
    assert "veggie tacos, snow pea salad, apple tartlets, tea service" in res1

    # Descriptive phrase
    res2 = asyncio.run(book_meeting("Wednesday 12:00-13:00", catering_menu_choice="Veggie Tacos"))
    assert "Successfully booked!" in res2
    assert "Veggie Taco Fiesta" in res2

    # In-text phrase
    res3 = asyncio.run(book_meeting("Thursday 12:00-13:00", reason="Team sync with the taco platter"))
    assert "Successfully booked!" in res3
    assert "Veggie Taco Fiesta" in res3


def test_book_meeting_default_menu_fallback() -> None:
    """AC5: Default to Menu Option 1 when catering is omitted."""
    res = asyncio.run(book_meeting("Friday 12:00-13:00", "Team lunch"))
    assert "Successfully booked!" in res
    assert "Buffalo Chicken Wrap Platter" in res
    assert "Selected by default" in res


def test_book_meeting_invalid_menu_warning_and_fallback() -> None:
    """AC6: Invalid catering selection warns user and falls back to Menu Option 1."""
    res = asyncio.run(book_meeting("Friday 12:00-13:00", catering_menu_choice="Menu 4"))
    assert "Successfully booked!" in res
    assert "Buffalo Chicken Wrap Platter" in res
    assert "Warning" in res
    assert "unrecognized" in res.lower()


