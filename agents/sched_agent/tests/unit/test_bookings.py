"""Tests for the Memory Bank booking store.

The client is faked; what is asserted is the call shape the service requires --
constant team scope, verbatim write, scope-keyed listing with an explicit page size.
"""

import asyncio
import json

import pytest

from app import bookings


class _FakeMemory:
    def __init__(self, fact: str, name: str | None):
        self.fact = fact
        self.name = name


class _FakeRetrieved:
    def __init__(self, fact: str, name: str | None):
        self.memory = _FakeMemory(fact, name)


class _FakePager:
    """Yields each stored fact with the resource name deletion addresses."""

    def __init__(self, entries: list[tuple[str, str]]):
        self._entries = list(entries)

    def __aiter__(self):
        async def _gen():
            for name, fact in self._entries:
                yield _FakeRetrieved(fact, name)

        return _gen()


class _FakeMemories:
    """Records how it was called so the call shape can be asserted."""

    def __init__(self, facts: list[str] | None = None):
        self.facts = facts if facts is not None else []
        self.create_calls: list[dict] = []
        self.retrieve_calls: list[dict] = []
        self.delete_calls: list[str] = []
        # Names are stable across deletions, as the service's are: addressing by
        # position would let one delete shift the rest.
        self._names: list[str] = []
        self._issued = 0

    async def create(self, *, name, fact, scope, **kwargs):
        self.create_calls.append({"name": name, "fact": fact, "scope": scope, **kwargs})
        self.facts.append(fact)

    async def retrieve(self, *, name, scope, **kwargs):
        self.retrieve_calls.append({"name": name, "scope": scope, **kwargs})
        while len(self._names) < len(self.facts):
            self._names.append(f"memories/{self._issued}")
            self._issued += 1
        return _FakePager(list(zip(self._names, self.facts)))

    async def delete(self, *, name, **kwargs):
        self.delete_calls.append(name)
        index = self._names.index(name)
        del self._names[index]
        del self.facts[index]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeMemories:
    memories = _FakeMemories()
    monkeypatch.setenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", "12345")
    monkeypatch.setattr(bookings, "_memories", lambda: memories)
    monkeypatch.setattr(bookings, "_local_bookings", [])
    return memories


def test_team_scope_is_constant_and_user_independent() -> None:
    """The sentinel user_id makes the collection team-wide; changing it orphans
    every booking already written."""
    assert bookings.TEAM_SCOPE == {"app_name": "sched_agent", "user_id": "team"}


def test_write_uses_create_with_team_scope(fake: _FakeMemories) -> None:
    asyncio.run(bookings.add_booking("Friday 12:00-13:00", "Team lunch"))

    assert len(fake.create_calls) == 1
    call = fake.create_calls[0]
    assert call["scope"] == bookings.TEAM_SCOPE
    assert call["name"] == "reasoningEngines/12345"
    # Verbatim -- the generate/ingest paths would not guarantee this.
    assert call["fact"].startswith("booking:")
    assert json.loads(call["fact"][len("booking:"):])["time_slot"] == "Friday 12:00-13:00"


def test_read_is_scope_keyed_with_an_explicit_page_size(fake: _FakeMemories) -> None:
    """Unset, page_size silently yields only 3 memories."""
    asyncio.run(bookings.add_booking("Friday 12:00-13:00"))
    asyncio.run(bookings.list_bookings())

    call = fake.retrieve_calls[0]
    assert call["scope"] == bookings.TEAM_SCOPE
    assert call["simple_retrieval_params"]["page_size"] == 100
    # A similarity query would rank by distance and drop bookings.
    assert "similarity_search_params" not in call


def test_round_trip_preserves_fields(fake: _FakeMemories) -> None:
    asyncio.run(bookings.add_booking("Friday 12:00-13:00", "Team lunch"))
    listed = asyncio.run(bookings.list_bookings())

    assert len(listed) == 1
    assert listed[0]["time_slot"] == "Friday 12:00-13:00"
    assert listed[0]["reason"] == "Team lunch"
    assert listed[0]["booking_id"].startswith("bk_")


def test_reads_every_page_not_just_the_first(fake: _FakeMemories) -> None:
    for i in range(7):
        asyncio.run(bookings.add_booking(f"Slot {i}"))

    assert len(asyncio.run(bookings.list_bookings())) == 7


def test_foreign_memories_in_the_scope_are_ignored(fake: _FakeMemories) -> None:
    fake.facts.append("Sprint retrospective notes from Friday")
    fake.facts.append("booking:{not valid json")
    asyncio.run(bookings.add_booking("Friday 12:00-13:00"))

    listed = asyncio.run(bookings.list_bookings())
    assert len(listed) == 1
    assert listed[0]["time_slot"] == "Friday 12:00-13:00"


def test_falls_back_in_process_when_no_engine_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setattr(bookings, "_local_bookings", [])

    asyncio.run(bookings.add_booking("Friday 12:00-13:00"))
    assert len(asyncio.run(bookings.list_bookings())) == 1


def test_cancelling_deletes_the_matching_memory(fake: _FakeMemories) -> None:
    """Deletion addresses the memory's resource name, which only the retrieved
    memory carries -- a booking parsed from its fact cannot be traced back."""
    keep = asyncio.run(bookings.add_booking("Monday 12:00-13:00"))
    drop = asyncio.run(bookings.add_booking("Friday 12:00-13:00"))

    assert asyncio.run(bookings.delete_booking(drop["booking_id"])) is True

    assert fake.delete_calls == ["memories/1"]
    remaining = asyncio.run(bookings.list_bookings())
    assert [b["booking_id"] for b in remaining] == [keep["booking_id"]]


def test_cancelling_an_unknown_id_reports_it_and_deletes_nothing(
    fake: _FakeMemories,
) -> None:
    asyncio.run(bookings.add_booking("Monday 12:00-13:00"))

    assert asyncio.run(bookings.delete_booking("bk_does_not_exist")) is False

    assert fake.delete_calls == []
    assert len(asyncio.run(bookings.list_bookings())) == 1


def test_cancelling_frees_the_slot_for_the_whole_team(fake: _FakeMemories) -> None:
    """The scope is constant, so a cancellation is visible to every caller."""
    booking = asyncio.run(bookings.add_booking("Friday 12:00-13:00"))
    asyncio.run(bookings.delete_booking(booking["booking_id"]))

    assert asyncio.run(bookings.list_bookings()) == []
    assert fake.retrieve_calls[-1]["scope"] == bookings.TEAM_SCOPE


def test_foreign_memories_are_never_deleted(fake: _FakeMemories) -> None:
    """A scope may hold memories this module did not write."""
    fake.facts.append("Sprint retrospective notes from Friday")
    booking = asyncio.run(bookings.add_booking("Friday 12:00-13:00"))

    asyncio.run(bookings.delete_booking(booking["booking_id"]))

    assert fake.delete_calls == ["memories/1"]
    assert fake.facts == ["Sprint retrospective notes from Friday"]


def test_cancelling_falls_back_in_process_when_no_engine_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setattr(bookings, "_local_bookings", [])

    booking = asyncio.run(bookings.add_booking("Friday 12:00-13:00"))

    assert asyncio.run(bookings.delete_booking(booking["booking_id"])) is True
    assert asyncio.run(bookings.list_bookings()) == []
    assert asyncio.run(bookings.delete_booking(booking["booking_id"])) is False


def test_ids_are_unique_within_a_second(fake: _FakeMemories) -> None:
    """Cancellation resolves a booking by id, so ids built from whole seconds
    would let one cancellation remove a different meeting."""
    ids = {
        asyncio.run(bookings.add_booking(f"Slot {i}"))["booking_id"]
        for i in range(20)
    }

    assert len(ids) == 20


def test_clearing_all_requires_the_count_to_match(fake: _FakeMemories) -> None:
    """The count is the confirmation: a caller that guessed, or listed before
    someone else booked, must not clear the team's calendar."""
    for i in range(3):
        asyncio.run(bookings.add_booking(f"Slot {i}"))

    assert asyncio.run(bookings.delete_all_bookings(2)) == -1

    assert fake.delete_calls == []
    assert len(asyncio.run(bookings.list_bookings())) == 3


def test_clearing_all_deletes_every_booking_when_the_count_matches(
    fake: _FakeMemories,
) -> None:
    for i in range(3):
        asyncio.run(bookings.add_booking(f"Slot {i}"))

    assert asyncio.run(bookings.delete_all_bookings(3)) == 3
    assert asyncio.run(bookings.list_bookings()) == []


def test_clearing_all_leaves_foreign_memories_alone(fake: _FakeMemories) -> None:
    """Only bookings are counted and only bookings are deleted; the scope may
    hold memories this module did not write."""
    fake.facts.append("Sprint retrospective notes from Friday")
    asyncio.run(bookings.add_booking("Friday 12:00-13:00"))

    assert asyncio.run(bookings.delete_all_bookings(1)) == 1
    assert fake.facts == ["Sprint retrospective notes from Friday"]


def test_clearing_an_empty_collection_is_not_a_mismatch(fake: _FakeMemories) -> None:
    assert asyncio.run(bookings.delete_all_bookings(0)) == 0
    assert fake.delete_calls == []


def test_clearing_all_falls_back_in_process_when_no_engine_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setattr(bookings, "_local_bookings", [])

    asyncio.run(bookings.add_booking("Friday 12:00-13:00"))
    asyncio.run(bookings.add_booking("Monday 12:00-13:00"))

    assert asyncio.run(bookings.delete_all_bookings(1)) == -1
    assert len(asyncio.run(bookings.list_bookings())) == 2
    assert asyncio.run(bookings.delete_all_bookings(2)) == 2
    assert asyncio.run(bookings.list_bookings()) == []
