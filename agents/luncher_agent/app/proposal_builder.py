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

"""Deterministic text-based lunch proposal construction driven by a tool call.

The model calls :func:`format_lunch_proposal` with domain data and Python formats
the structured Markdown output and validates team attendance against the scheduling
agent's roster.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.tools import FunctionTool, ToolContext


ROLE_DESCRIPTION = (
    "You are the central Luncher Synthesizer Agent. You receive context containing "
    "strategic corporate priorities, team schedule options, and curated thematic catering menus "
    "from the catering agent.\n\n"
    "Synthesize them into a single structured team lunch proposal and call the "
    "`format_lunch_proposal` tool to produce the final response. Frame the lunch "
    "around the strategic objective it serves, include every team member by name, "
    "carry across who cannot attend each slot exactly as the scheduling agent reported it, "
    "and extract and forward all 3 thematic catering menus and any active dietary accommodations "
    "from the catering agent into `format_lunch_proposal`.\n\n"
    "BOOKING TURNS. When the user confirms or requests to book a specific slot (e.g., 'Book Tuesday 12:00' "
    "or 'Option 1 works'), do not call `format_lunch_proposal`. Delegate the selected slot and catering menu "
    "to the scheduling agent and reply with a concise confirmation of at most four bullets:\n"
    "* **Time Slot**: [selected slot]\n"
    "* **Attendees**: [list of attendees]\n"
    "* **Booking ID**: [booking id]\n"
    "* **Catering Menu**: [Theme name: selected items]\n\n"
    "Say each fact once. No extra recap or pleasantries."
)

SCHEDULING_AGENT_NAME = "scheduling_agent"

# The roster line the scheduling agent opens its shortlist with,
# e.g. "Team (8): Liam, Diego, Dan, ...".
_ROSTER_LINE = re.compile(
    r"Team\s*\**\s*\(\s*(\d+)\s*\)\s*\**\s*:\s*(.+)", re.IGNORECASE
)


def _split_names(text: str) -> list[str]:
    """Splits a written list of names, tolerating 'and' and trailing punctuation."""
    return [
        stripped
        for name in re.split(r",|\band\b", text)
        if (stripped := name.strip(" .;*_`"))
    ]


def _roster_from_text(roster_text: str) -> list[str] | None:
    """Reads the roster the scheduling agent named, or None if it didn't name one."""
    for line in roster_text.splitlines():
        match = _ROSTER_LINE.search(line)
        if not match:
            continue
        names = _split_names(match.group(2))
        if len(names) == int(match.group(1)):
            return names
    return None


def _scheduling_agent_text(tool_context: ToolContext | None) -> str:
    """Concatenates what the scheduling agent said during this invocation."""
    if tool_context is None:
        return ""
    session = getattr(tool_context, "session", None)
    if session is None:
        return ""

    chunks: list[str] = []
    for event in getattr(session, "events", []) or []:
        if getattr(event, "author", None) != SCHEDULING_AGENT_NAME:
            continue
        tool_inv_id = getattr(tool_context, "invocation_id", None)
        event_inv_id = getattr(event, "invocation_id", None)
        if tool_inv_id and event_inv_id and event_inv_id != tool_inv_id:
            continue
        for part in getattr(getattr(event, "content", None), "parts", None) or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
        if getattr(event, "output", None) and isinstance(event.output, str):
            chunks.append(event.output)
    return "\n".join(chunks)


def _unsupported_attendees(attendees: list[str], roster_text: str) -> list[str]:
    """Returns the attendees the scheduling agent never mentioned."""
    haystack = roster_text.casefold()
    return [name for name in attendees if name.casefold() not in haystack]


def _format_item_name(item: Any) -> str:
    """Extracts a clean name from an item dict or string."""
    if isinstance(item, dict):
        return str(item.get("name", "")).strip()
    return str(item).strip()


def build_lunch_proposal_markdown(
    *,
    title: str,
    rationale: str,
    attendees: list[str],
    time_slots: list[dict],
    recommended_slot: str,
    catering_menus: list[dict],
    accommodations: str = "",
) -> str:
    """Builds the structured Markdown text for a lunch proposal."""
    if not time_slots:
        raise ValueError("at least one time slot is required")

    values = [slot["value"] for slot in time_slots]
    if recommended_slot not in values:
        raise ValueError(
            f"recommended_slot {recommended_slot!r} is not one of the offered slots {values!r}"
        )

    if catering_menus is None or len(catering_menus) != 3:
        count = len(catering_menus) if catering_menus is not None else 0
        raise ValueError(
            f"Exactly 3 thematic catering menus are required, got {count}"
        )

    required_courses = ("mains", "sides", "beverages", "desserts")
    for index, menu in enumerate(catering_menus, start=1):
        if not isinstance(menu, dict):
            raise ValueError(f"Catering menu {index} must be a dictionary")
        if not menu.get("theme_name") or not str(menu["theme_name"]).strip():
            raise ValueError(f"Catering menu {index} is missing a valid 'theme_name'")
        for course in required_courses:
            if course not in menu or not menu[course]:
                raise ValueError(
                    f"Catering menu {index} ({menu.get('theme_name')}) is missing or has empty '{course}'"
                )

    slots_formatted = []
    for index, slot in enumerate(time_slots, start=1):
        is_rec = " ⭐ *Recommended*" if slot["value"] == recommended_slot else ""
        absent = slot.get("absent") or "Everyone can attend"
        slots_formatted.append(
            f"{index}. **{slot['label']}**{is_rec}\n   * *Absences*: {absent}"
        )

    slots_section = "\n".join(slots_formatted)
    attendees_str = ", ".join(attendees)

    menus_formatted = []
    for index, menu in enumerate(catering_menus, start=1):
        theme = str(menu["theme_name"]).strip()
        mains_str = ", ".join(
            name
            for item in menu["mains"]
            if (name := _format_item_name(item))
        )
        sides_str = ", ".join(
            name
            for item in menu["sides"]
            if (name := _format_item_name(item))
        )
        beverages_str = ", ".join(
            name
            for item in menu["beverages"]
            if (name := _format_item_name(item))
        )
        desserts_str = ", ".join(
            name
            for item in menu["desserts"]
            if (name := _format_item_name(item))
        )
        menus_formatted.append(
            f"{index}. **{theme}**\n"
            f"   * *Mains*: {mains_str}\n"
            f"   * *Sides*: {sides_str}\n"
            f"   * *Beverages*: {beverages_str}\n"
            f"   * *Desserts*: {desserts_str}"
        )
    menus_section = "\n".join(menus_formatted)

    proposal_parts = [
        f"# {title}",
        f"**Strategic Rationale**: {rationale}",
        f"### Included Team Members\n{attendees_str}",
        f"### Proposed Time Slots\n{slots_section}",
        f"### Proposed Catering Menus\n{menus_section}",
    ]

    if accommodations and accommodations.strip():
        acc_text = accommodations.strip()
        if not acc_text.startswith("### Dietary Accommodations"):
            proposal_parts.append(f"### Dietary Accommodations\n{acc_text}")
        else:
            proposal_parts.append(acc_text)

    first_slot_label = time_slots[0]["label"]
    proposal_parts.append(
        f"---\n*To confirm, reply with your preferred time slot (e.g., \"Book {first_slot_label}\").*"
    )

    return "\n\n".join(proposal_parts)


def format_lunch_proposal(
    title: str,
    rationale: str,
    attendees: list[str],
    slot_labels: list[str],
    slot_values: list[str],
    slot_absentees: list[str],
    recommended_slot: str,
    catering_menus: list[dict],
    tool_context: ToolContext | None = None,
    accommodations: str = "",
) -> str:
    """Formats the team lunch proposal as structured Markdown text.

    Every argument is a flat list of strings. Lists that pair up (slot_labels with
    slot_values and slot_absentees) must be the same length and in the same order --
    entry i of one describes entry i of the other.

    Args:
        title: Short name for the lunch, referencing the strategic objective it serves.
        rationale: One or two sentences on which corporate priority this lunch advances.
        attendees: The team exactly as the scheduling agent's "Team (N): ..." line
            names it, one per entry, copied verbatim -- do not expand a first name
            into a full name, invent anyone, or use a placeholder. This is the whole
            team, not the subset free at the recommended slot.
        slot_labels: Human-readable label per time slot, with attendance included
            (e.g. "Tue 12 Aug, 12:00-13:00 (8 of 8 free)"). Include ALL viable options
            you were given, typically 2-4.
        slot_values: ISO timestamp per slot (e.g. "2026-08-12T12:00"), same order and
            length as slot_labels.
        slot_absentees: Who cannot attend each slot, same order and length as
            slot_labels -- the names the scheduling agent gave for that slot,
            comma-separated (e.g. "Maya, Kai"). Use an empty string for a slot the
            whole team can make. Every name must be one the scheduling agent
            listed.
        recommended_slot: The slot_values entry you recommend; must be one of them.
        catering_menus: Exactly 3 thematic catering menus from the catering agent,
            each containing theme_name, mains, sides, beverages, and desserts.
        tool_context: ADK tool context for inspecting session events.
        accommodations: Optional note on active dietary accommodations filtered for
            the team (e.g. "Filtered to accommodate: Peanut allergy (Alice)").
    """
    try:
        if len(slot_labels) != len(slot_values):
            raise ValueError(
                f"slot_labels has {len(slot_labels)} entries but slot_values has "
                f"{len(slot_values)}; they must correspond one to one"
            )
        if len(slot_absentees) != len(slot_labels):
            raise ValueError(
                f"slot_absentees has {len(slot_absentees)} entries but slot_labels has "
                f"{len(slot_labels)}; give one entry per slot, empty where everyone "
                f"can attend"
            )
        roster_text = _scheduling_agent_text(tool_context)
        roster = _roster_from_text(roster_text)
        if roster is not None:
            missing = [
                n
                for n in roster
                if n.casefold() not in {a.casefold() for a in attendees}
            ]
            extra = [
                a
                for a in attendees
                if a.casefold() not in {n.casefold() for n in roster}
            ]
            if missing or extra:
                raise ValueError(
                    f"attendees must be exactly the team the scheduling agent named "
                    f"({', '.join(roster)})"
                    + (f"; missing {', '.join(missing)}" if missing else "")
                    + (f"; not on the team: {', '.join(extra)}" if extra else "")
                )
        elif roster_text:
            invented = _unsupported_attendees(attendees, roster_text)
            if invented:
                raise ValueError(
                    f"these attendees are not on the roster the scheduling agent "
                    f"returned: {', '.join(invented)}. Use the names it gave you, "
                    f"spelled the same way"
                )

        if roster is not None:
            known = {n.casefold() for n in roster}
            unknown = [
                name
                for entry in slot_absentees
                for name in _split_names(entry)
                if name.casefold() not in known
            ]
            if unknown:
                raise ValueError(
                    f"slot_absentees names people who are not on the team: "
                    f"{', '.join(unknown)}. Use only the names in "
                    f"({', '.join(roster)})"
                )

        markdown = build_lunch_proposal_markdown(
            title=title,
            rationale=rationale,
            attendees=attendees,
            time_slots=[
                {"label": label, "value": value, "absent": absent}
                for label, value, absent in zip(slot_labels, slot_values, slot_absentees)
            ],
            recommended_slot=recommended_slot,
            catering_menus=catering_menus,
            accommodations=accommodations,
        )
        return markdown
    except (ValueError, KeyError, TypeError) as error:
        return f"Could not format the proposal: {error}"


format_lunch_proposal_tool = FunctionTool(format_lunch_proposal)
