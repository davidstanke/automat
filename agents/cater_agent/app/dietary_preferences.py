# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Team-scoped dietary preference memory management backed by Agent Platform Memory Bank.

Stores preferences under constant team scope {"app_name": "cater_agent", "user_id": "team"}.
Supports local in-process fallback when GOOGLE_CLOUD_AGENT_ENGINE_ID is unset.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import datetime
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Constant team scope for all dietary preferences
TEAM_SCOPE: dict[str, str] = {
    "app_name": "cater_agent",
    "user_id": "team",
}

# Prefix for facts stored in Memory Bank
_FACT_PREFIX = "dietary_pref:"

# Page size for Memory Bank retrieval
_PAGE_SIZE = 100

# Environment variable denoting Agent Engine ID
_ENGINE_ID_VAR = "GOOGLE_CLOUD_AGENT_ENGINE_ID"

# Allowed preference types
ALLOWED_PREFERENCE_TYPES: frozenset[str] = frozenset(
    {"allergy", "restriction", "dislike", "like"}
)

# Offline fallback list
_local_preferences: list[dict[str, Any]] = []

# Sanitization regular expressions
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCRIPT_TAGS_RE = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.IGNORECASE)
_HTML_TAGS_RE = re.compile(
    r"<[^>]+>|<\s*/?\s*(?:script|img|iframe|style|object|embed|svg)[^>]*>?",
    re.IGNORECASE,
)
_EVENT_HANDLERS_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_PROMPT_INJECTION_RE = re.compile(
    r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above|past)?\s*instructions\b",
    re.IGNORECASE,
)
_SQL_PUNCTUATION_RE = re.compile(r"--|;|/\*.*?\*/")
_SQL_KEYWORDS_RE = re.compile(
    r"\b(?:DROP|TABLE|UNION|SELECT|INSERT|INTO|DELETE|TRUNCATE|UPDATE|EXEC|EXECUTE|ALTER|VALUES)\b",
    re.IGNORECASE,
)


def sanitize_input(val: str) -> str:
    """Strips harmful injection characters, SQL control statements, and script tags."""
    if not isinstance(val, str):
        val = str(val) if val is not None else ""
    if not val:
        return ""

    # Strip null bytes and non-printable control characters
    val = _CONTROL_CHARS_RE.sub("", val)

    # Strip script blocks with tags and contents
    val = _SCRIPT_TAGS_RE.sub("", val)

    # Strip any HTML/XML tags
    val = _HTML_TAGS_RE.sub("", val)

    # Strip event handler attributes (e.g., onerror=)
    val = _EVENT_HANDLERS_RE.sub("", val)

    # Strip prompt injection phrases
    val = _PROMPT_INJECTION_RE.sub("", val)

    # Strip SQL comments and statement terminators (; and --)
    val = _SQL_PUNCTUATION_RE.sub("", val)

    # Strip dangerous SQL keywords
    val = _SQL_KEYWORDS_RE.sub("", val)

    # Collapse multiple whitespace and trim ends
    val = re.sub(r"[ \t]+", " ", val).strip()

    return val


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
        location=os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
        or os.getenv("GOOGLE_CLOUD_LOCATION"),
    )
    return client.aio.agent_engines.memories


async def add_preference(
    person_name: str,
    preference_type: str,
    details: str,
) -> dict[str, Any]:
    """Records a dietary preference in the team collection and returns it."""
    clean_name = sanitize_input(person_name)
    clean_details = sanitize_input(details)

    normalized_type = (preference_type or "").strip().lower()
    if normalized_type not in ALLOWED_PREFERENCE_TYPES:
        raise ValueError(
            f"Invalid preference_type '{preference_type}'. "
            f"Must be one of: {', '.join(sorted(ALLOWED_PREFERENCE_TYPES))}"
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    record: dict[str, Any] = {
        "person_name": clean_name,
        "preference_type": normalized_type,
        "details": clean_details,
        "created_at": now.isoformat(),
    }

    memories = _memories()
    if memories is None:
        logger.warning(
            "%s is unset -- preference stored in-process only.", _ENGINE_ID_VAR
        )
        _local_preferences.append(record)
        return record

    await memories.create(
        name=_engine_name(),
        fact=_FACT_PREFIX + json.dumps(record, sort_keys=True),
        scope=TEAM_SCOPE,
    )
    logger.info("Stored dietary preference for %s in Memory Bank", clean_name)
    return record


async def _stored_preferences(
    memories: Any,
) -> AsyncIterator[tuple[str | None, dict[str, Any]]]:
    """Yields ``(memory resource name, preference)`` for the team collection."""
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

        raw_json = fact[len(_FACT_PREFIX) :]
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping unparseable dietary preference memory: %.80s", fact)
            continue

        if not isinstance(data, dict):
            logger.warning(
                "Skipping unparseable dietary preference memory (not a JSON object): %.80s",
                fact,
            )
            continue

        required_keys = {"person_name", "preference_type", "details", "created_at"}
        if not required_keys.issubset(data.keys()):
            logger.warning(
                "Skipping unparseable dietary preference memory (missing required fields): %.80s",
                fact,
            )
            continue

        pref_type = str(data["preference_type"]).strip().lower()
        if pref_type not in ALLOWED_PREFERENCE_TYPES:
            logger.warning(
                "Skipping unparseable dietary preference memory (invalid preference_type): %.80s",
                fact,
            )
            continue

        pref: dict[str, Any] = {
            "person_name": str(data["person_name"]),
            "preference_type": pref_type,
            "details": str(data["details"]),
            "created_at": str(data["created_at"]),
        }
        yield getattr(memory, "name", None), pref


async def list_preferences(person_name: str | None = None) -> list[dict[str, Any]]:
    """Returns dietary preferences in the team collection, optionally filtered by person_name."""
    memories = _memories()

    if memories is None:
        logger.warning(
            "%s is unset -- reading in-process preferences.", _ENGINE_ID_VAR
        )
        prefs = list(_local_preferences)
    else:
        prefs = [pref async for _, pref in _stored_preferences(memories)]
        logger.info("Retrieved %d dietary preferences from Memory Bank", len(prefs))

    prefs.sort(key=lambda p: p.get("created_at", ""))

    if person_name is not None:
        target = person_name.strip().lower()
        prefs = [p for p in prefs if p.get("person_name", "").strip().lower() == target]

    return prefs


async def delete_preference(person_name: str, details: str) -> bool:
    """Removes a matching dietary preference from the team collection. Returns whether it existed."""
    memories = _memories()
    target_name = person_name.strip().lower()
    target_details = details.strip().lower()

    if memories is None:
        logger.warning(
            "%s is unset -- deleting from in-process preferences.", _ENGINE_ID_VAR
        )
        for i, pref in enumerate(_local_preferences):
            if (
                pref.get("person_name", "").strip().lower() == target_name
                and pref.get("details", "").strip().lower() == target_details
            ):
                _local_preferences.pop(i)
                return True
        return False

    async for name, pref in _stored_preferences(memories):
        if (
            pref.get("person_name", "").strip().lower() == target_name
            and pref.get("details", "").strip().lower() == target_details
        ):
            if not name:
                logger.warning(
                    "Dietary preference for %s (%s) has no resource name; cannot delete.",
                    person_name,
                    details,
                )
                return False
            await memories.delete(name=name)
            logger.info(
                "Deleted dietary preference for %s (%s) from Memory Bank",
                person_name,
                details,
            )
            return True

    logger.info("No dietary preference for %s (%s) to delete", person_name, details)
    return False


async def clear_all_preferences(expected_count: int) -> int:
    """Removes every dietary preference, but only if there are exactly ``expected_count``.

    Returns the number deleted, or -1 when the count did not match and nothing was touched.
    """
    memories = _memories()

    if memories is None:
        logger.warning(
            "%s is unset -- clearing in-process preferences.", _ENGINE_ID_VAR
        )
        if len(_local_preferences) != expected_count:
            return -1
        deleted = len(_local_preferences)
        _local_preferences.clear()
        return deleted

    named = [(name, pref) async for name, pref in _stored_preferences(memories)]
    if len(named) != expected_count:
        logger.info(
            "Refusing to clear preferences: caller expected %d, found %d",
            expected_count,
            len(named),
        )
        return -1

    deleted = 0
    for name, pref in named:
        if not name:
            logger.warning(
                "Dietary preference for %s (%s) has no resource name; cannot delete.",
                pref.get("person_name"),
                pref.get("details"),
            )
            continue
        await memories.delete(name=name)
        deleted += 1

    logger.info("Deleted %d dietary preferences from Memory Bank", deleted)
    return deleted


__all__ = [
    "ALLOWED_PREFERENCE_TYPES",
    "TEAM_SCOPE",
    "add_preference",
    "clear_all_preferences",
    "delete_preference",
    "list_preferences",
    "sanitize_input",
]
