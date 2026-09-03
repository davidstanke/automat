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


def test_book_meeting_with_catering_items_list() -> None:
    res = asyncio.run(
        book_meeting(
            "Tuesday 12:00-13:00",
            "Strategy lunch",
            catering_theme="Baja Fiesta",
            catering_items=["Grilled Mahi Mahi Tacos", "Tortilla Chips"],
        )
    )
    assert "Successfully booked!" in res
    assert "bk_" in res
    assert len(bookings._local_bookings) == 1
    assert bookings._local_bookings[0]["catering_menu"] == {
        "theme_name": "Baja Fiesta",
        "selected_items": ["Grilled Mahi Mahi Tacos", "Tortilla Chips"],
    }


def test_book_meeting_with_catering_items_comma_separated_string() -> None:
    res = asyncio.run(
        book_meeting(
            "Wednesday 12:00-13:00",
            "All-hands lunch",
            catering_theme="Artisan Deli",
            catering_items="Turkey Club, Caesar Salad, Sparkling Water",
        )
    )
    assert "Successfully booked!" in res
    assert len(bookings._local_bookings) == 1
    assert bookings._local_bookings[0]["catering_menu"] == {
        "theme_name": "Artisan Deli",
        "selected_items": ["Turkey Club", "Caesar Salad", "Sparkling Water"],
    }


def test_book_meeting_with_catering_items_string_whitespace_and_empty_entries() -> None:
    asyncio.run(
        book_meeting(
            "Thursday 12:00-13:00",
            catering_theme="Italian Trattoria",
            catering_items="  Lasagna  , , Tiramisu , ",
        )
    )
    assert len(bookings._local_bookings) == 1
    assert bookings._local_bookings[0]["catering_menu"] == {
        "theme_name": "Italian Trattoria",
        "selected_items": ["Lasagna", "Tiramisu"],
    }


def test_book_meeting_passes_structured_dict_to_add_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_calls: list[dict] = []
    orig_add = bookings.add_booking

    async def mock_add_booking(*args, **kwargs):
        recorded_calls.append({"args": args, "kwargs": kwargs})
        return await orig_add(*args, **kwargs)

    monkeypatch.setattr(bookings, "add_booking", mock_add_booking)
    asyncio.run(
        book_meeting(
            time_slot="Friday 12:00-13:00",
            reason="Sprint demo",
            catering_theme="Pan-Asian Bistro",
            catering_items=["Pad Thai", "Spring Rolls"],
        )
    )
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    kwargs = call["kwargs"]
    args = call["args"]
    time_slot = kwargs.get("time_slot") or (args[0] if len(args) > 0 else None)
    reason = kwargs.get("reason") or (args[1] if len(args) > 1 else None)
    catering_menu = kwargs.get("catering_menu") or (args[2] if len(args) > 2 else None)

    assert time_slot == "Friday 12:00-13:00"
    assert reason == "Sprint demo"
    assert catering_menu == {
        "theme_name": "Pan-Asian Bistro",
        "selected_items": ["Pad Thai", "Spring Rolls"],
    }


def test_book_meeting_without_catering_omits_or_nils_catering_menu() -> None:
    res = asyncio.run(book_meeting("Monday 10:00-11:00 AM", "Weekly standup"))
    assert "Successfully booked!" in res
    assert len(bookings._local_bookings) == 1
    assert bookings._local_bookings[0].get("catering_menu") is None


def test_book_meeting_empty_catering_arguments_backwards_compatible() -> None:
    res = asyncio.run(
        book_meeting(
            "Monday 10:00-11:00 AM",
            "Weekly standup",
            catering_theme="",
            catering_items="",
        )
    )
    assert "Successfully booked!" in res
    assert len(bookings._local_bookings) == 1
    assert bookings._local_bookings[0].get("catering_menu") is None


def test_get_bookings_with_catering_booking() -> None:
    asyncio.run(
        book_meeting(
            "Friday 12:00-13:00",
            "Celebration",
            catering_theme="Baja Fiesta",
            catering_items=["Tacos"],
        )
    )
    listed = asyncio.run(get_bookings())
    assert "Friday 12:00-13:00" in listed
    assert "Celebration" in listed


def test_sched_agent_instruction_captures_catering_details() -> None:
    from app.agent import root_agent

    instruction = root_agent.instruction.lower()
    assert "catering" in instruction

