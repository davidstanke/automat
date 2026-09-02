import asyncio

import pytest

from app import bookings
from app.tools import (
    get_team_members,
    book_meeting,
    get_bookings,
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
