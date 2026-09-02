"""Team-scoped booking storage backed by Agent Platform Memory Bank.

Calls the API directly rather than via ADK's memory service, which cannot do
either half: ``ToolContext.add_memory`` scopes writes with the *session's*
``user_id`` (whichever caller invoked us, not a constant team scope), and
``search_memory`` is similarity-only where listing needs
``retrieve(simple_retrieval_params=...)``.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# Immutable per memory: changing either value orphans every existing booking.
TEAM_SCOPE: dict[str, str] = {
    "app_name": "sched_agent",
    "user_id": "team",
}

# Marks our memories so anything else in the scope is skipped, not parsed.
_FACT_PREFIX = "booking:"

# Unset, the service returns at most 3 -- silently, with no truncation flag.
_PAGE_SIZE = 100

# Set by Agent Runtime. Absent on Cloud Run and when running locally.
_ENGINE_ID_VAR = "GOOGLE_CLOUD_AGENT_ENGINE_ID"

# Offline fallback only: per-process and lost on restart.
_local_bookings: list[dict[str, Any]] = []


def _engine_name() -> str | None:
    """Resource name of the engine holding the memory bank, if configured."""
    engine_id = os.getenv(_ENGINE_ID_VAR)
    return f"reasoningEngines/{engine_id}" if engine_id else None


def _memories():
    """Async Memory Bank client, or None when no engine is configured."""
    if not _engine_name():
        return None
    import vertexai

    client = vertexai.Client(
        project=os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
        # The engine's own region, which may differ from the deploy region.
        location=os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
        or os.getenv("GOOGLE_CLOUD_LOCATION"),
    )
    return client.aio.agent_engines.memories


def _new_booking(time_slot: str, reason: str = "") -> dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        # Seconds alone collide when two bookings land in the same second, and
        # cancellation addresses a booking by this id.
        "booking_id": f"bk_{int(now.timestamp())}_{uuid.uuid4().hex[:6]}",
        "time_slot": time_slot,
        "reason": reason,
        "booked_at": now.isoformat(),
    }


async def add_booking(time_slot: str, reason: str = "") -> dict[str, Any]:
    """Records a booking in the team collection and returns it."""
    booking = _new_booking(time_slot, reason)
    memories = _memories()

    if memories is None:
        logger.warning("%s is unset -- booking stored in-process only.", _ENGINE_ID_VAR)
        _local_bookings.append(booking)
        return booking

    # create() writes verbatim; the generate/ingest paths LLM-extract instead.
    await memories.create(
        name=_engine_name(),
        fact=_FACT_PREFIX + json.dumps(booking, sort_keys=True),
        scope=TEAM_SCOPE,
    )
    logger.info("Stored booking %s in Memory Bank", booking["booking_id"])
    return booking


async def _stored_bookings(memories) -> AsyncIterator[tuple[str | None, dict[str, Any]]]:
    """Yields ``(memory resource name, booking)`` for the team collection.

    The resource name is what deletion addresses, and it exists only on the
    retrieved memory -- a booking parsed out of its fact cannot be traced back.
    """
    # Scope-keyed listing; similarity search would silently omit low-ranked rows.
    pager = await memories.retrieve(
        name=_engine_name(),
        scope=TEAM_SCOPE,
        simple_retrieval_params={"page_size": _PAGE_SIZE},
    )

    async for retrieved in pager:
        memory = getattr(retrieved, "memory", None)
        fact = getattr(memory, "fact", None)
        if not fact or not fact.startswith(_FACT_PREFIX):
            continue
        try:
            booking = json.loads(fact[len(_FACT_PREFIX):])
        except json.JSONDecodeError:
            logger.warning("Skipping unparseable booking memory: %.80s", fact)
            continue
        yield getattr(memory, "name", None), booking


async def list_bookings() -> list[dict[str, Any]]:
    """Returns every booking in the team collection, oldest first."""
    memories = _memories()

    if memories is None:
        logger.warning("%s is unset -- reading in-process bookings.", _ENGINE_ID_VAR)
        return list(_local_bookings)

    bookings = [booking async for _, booking in _stored_bookings(memories)]
    bookings.sort(key=lambda b: b.get("booked_at", ""))
    logger.info("Retrieved %d bookings from Memory Bank", len(bookings))
    return bookings


async def delete_booking(booking_id: str) -> bool:
    """Removes a booking from the team collection. Returns whether it existed."""
    memories = _memories()

    if memories is None:
        logger.warning("%s is unset -- deleting from in-process bookings.", _ENGINE_ID_VAR)
        remaining = [b for b in _local_bookings if b.get("booking_id") != booking_id]
        found = len(remaining) != len(_local_bookings)
        _local_bookings[:] = remaining
        return found

    async for name, booking in _stored_bookings(memories):
        if booking.get("booking_id") != booking_id:
            continue
        if not name:
            logger.warning("Booking %s has no resource name; cannot delete.", booking_id)
            return False
        await memories.delete(name=name)
        logger.info("Deleted booking %s from Memory Bank", booking_id)
        return True

    logger.info("No booking %s to delete", booking_id)
    return False


async def delete_all_bookings(expected_count: int) -> int:
    """Removes every booking, but only if there are exactly ``expected_count``.

    Returns the number deleted, or -1 when the count did not match and nothing
    was touched. The caller has to have listed the collection immediately before,
    which is what stops the whole team's calendar going on a vague instruction.
    """
    memories = _memories()

    if memories is None:
        logger.warning("%s is unset -- clearing in-process bookings.", _ENGINE_ID_VAR)
        if len(_local_bookings) != expected_count:
            return -1
        deleted = len(_local_bookings)
        _local_bookings.clear()
        return deleted

    # Collected before deleting anything, so a mismatch costs nothing.
    named = [(name, b) async for name, b in _stored_bookings(memories)]
    if len(named) != expected_count:
        logger.info(
            "Refusing to clear bookings: caller expected %d, found %d",
            expected_count,
            len(named),
        )
        return -1

    deleted = 0
    for name, booking in named:
        if not name:
            logger.warning(
                "Booking %s has no resource name; cannot delete.",
                booking.get("booking_id"),
            )
            continue
        await memories.delete(name=name)
        deleted += 1

    logger.info("Deleted %d bookings from Memory Bank", deleted)
    return deleted
