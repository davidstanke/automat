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
the structured Markdown output, validates team attendance against the scheduling
agent's roster, and incorporates catering menu options.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.tools import FunctionTool, ToolContext


ROLE_DESCRIPTION = (
    "You are the central Luncher Synthesizer Agent. You receive context containing "
    "strategic corporate priorities, team schedule options, and catering menu options.\n\n"
    "Synthesize them into a single structured team lunch proposal and call the "
    "`format_lunch_proposal` tool to produce the final response. Frame the lunch "
    "around the strategic objective it serves, include every team member by name, "
    "carry across who cannot attend each slot exactly as the scheduling agent reported it, "
    "and include the 3 catering menu options from the catering agent.\n\n"
    "BOOKING TURNS. When the user confirms or requests to book a specific slot (e.g., 'Book Tuesday 12:00' "
    "or 'Option 1 with Menu 2'), do not call `format_lunch_proposal`. Reply with a concise confirmation "
    "of at most four bullets:\n"
    "* **Time Slot**: [selected slot]\n"
    "* **Attendees**: [list of attendees]\n"
    "* **Booking ID**: [booking id or 'Confirmed']\n"
    "* **Catering Menu**: [selected catering menu or Menu Option 1 (Default)]\n\n"
    "Say each fact once. No extra recap or pleasantries."
)

SCHEDULING_AGENT_NAME = "scheduling_agent"
CATER_AGENT_NAMES = ("cater_agent", "catering_agent")

DEFAULT_MOCK_MENUS: list[dict[str, Any]] = [
    {
        "menu_id": "menu_1",
        "name": "Buffalo Chicken Wrap",
        "items": [
            "buffalo chicken wrap",
            "mixed greens salad",
            "chocolate cookie",
            "assorted sodas",
        ],
    },
    {
        "menu_id": "menu_2",
        "name": "Veggie Tacos",
        "items": [
            "veggie tacos",
            "snow pea salad",
            "apple tartlets",
            "tea service",
        ],
    },
    {
        "menu_id": "menu_3",
        "name": "Lamb Vindaloo",
        "items": [
            "lamb vindaloo",
            "spiced cauliflower",
            "naan",
            "orange-mint spa water",
        ],
    },
]

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


def _scheduling_agent_text(tool_context: ToolContext) -> str:
    """Concatenates what the scheduling agent said during this invocation."""
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


def _cater_agent_text(tool_context: ToolContext) -> str:
    """Concatenates what the catering agent said during this invocation."""
    session = getattr(tool_context, "session", None)
    if session is None:
        return ""

    chunks: list[str] = []
    for event in getattr(session, "events", []) or []:
        if getattr(event, "author", None) not in CATER_AGENT_NAMES:
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


def _check_catering_unavailable(cater_text: str, tool_context: ToolContext) -> bool:
    """Detects if cater_agent errored, timed out, or returned an error message."""
    session = getattr(tool_context, "session", None)
    if session is not None:
        for event in getattr(session, "events", []) or []:
            if getattr(event, "author", None) in CATER_AGENT_NAMES:
                if getattr(event, "error", None) or getattr(event, "exception", None):
                    return True
    if not cater_text.strip():
        return False
    lower = cater_text.lower()
    if "error" in lower or "timeout" in lower or "unavailable" in lower or "failed" in lower:
        return True
    return False


def _unsupported_attendees(attendees: list[str], roster_text: str) -> list[str]:
    """Returns the attendees the scheduling agent never mentioned."""
    haystack = roster_text.casefold()
    return [name for name in attendees if name.casefold() not in haystack]


def build_lunch_proposal_markdown(
    *,
    title: str,
    rationale: str,
    attendees: list[str],
    time_slots: list[dict],
    recommended_slot: str,
    catering_menus: list[dict] | None = None,
    catering_unavailable: bool = False,
) -> str:
    """Builds the structured Markdown text for a lunch proposal."""
    if not time_slots:
        raise ValueError("at least one time slot is required")

    values = [slot["value"] for slot in time_slots]
    if recommended_slot not in values:
        raise ValueError(
            f"recommended_slot {recommended_slot!r} is not one of the offered slots {values!r}"
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

    if catering_unavailable:
        catering_section = (
            "### Catering Menu Options\n"
            "*Catering menu suggestions are temporarily unavailable.*"
        )
    else:
        menus = catering_menus if catering_menus is not None else DEFAULT_MOCK_MENUS
        menu_lines = []
        for idx, menu in enumerate(menus, start=1):
            name = menu.get("name", f"Option {idx}")
            items_list = menu.get("items", [])
            items_str = ", ".join(items_list) if isinstance(items_list, list) else str(items_list)
            menu_lines.append(f"{idx}. **Menu Option {idx}: {name}**\n   * *Items*: {items_str}")
        catering_section = "### Catering Menu Options\n" + "\n".join(menu_lines)

    footer = (
        "---\n"
        f"*To confirm, reply with your preferred time slot and catering menu "
        f"(e.g., \"Book {time_slots[0]['label']} with Menu 1\").*"
    )

    return (
        f"# {title}\n\n"
        f"**Strategic Rationale**: {rationale}\n\n"
        f"### Included Team Members\n"
        f"{attendees_str}\n\n"
        f"### Proposed Time Slots\n"
        f"{slots_section}\n\n"
        f"{catering_section}\n\n"
        f"{footer}"
    )


def format_lunch_proposal(
    title: str,
    rationale: str,
    attendees: list[str],
    slot_labels: list[str],
    slot_values: list[str],
    slot_absentees: list[str],
    recommended_slot: str,
    tool_context: ToolContext,
    catering_menus: list[dict] | list[str] | None = None,
    catering_unavailable: bool = False,
) -> str:
    """Formats the team lunch proposal as structured Markdown text with catering options.

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
        tool_context: Tool context containing session events from sub-agents.
        catering_menus: Optional custom catering menus list. Defaults to 3 mock menus.
        catering_unavailable: Flag indicating if catering service failed or is unavailable.
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

        cater_text = _cater_agent_text(tool_context)
        is_catering_unavailable = catering_unavailable or _check_catering_unavailable(
            cater_text, tool_context
        )

        resolved_menus = None
        if catering_menus and isinstance(catering_menus, list):
            if isinstance(catering_menus[0], dict):
                resolved_menus = catering_menus
            elif isinstance(catering_menus[0], str):
                resolved_menus = [
                    {"name": m, "items": [m]} for m in catering_menus
                ]

        markdown = build_lunch_proposal_markdown(
            title=title,
            rationale=rationale,
            attendees=attendees,
            time_slots=[
                {"label": label, "value": value, "absent": absent}
                for label, value, absent in zip(slot_labels, slot_values, slot_absentees)
            ],
            recommended_slot=recommended_slot,
            catering_menus=resolved_menus,
            catering_unavailable=is_catering_unavailable,
        )
        return markdown
    except (ValueError, KeyError, TypeError) as error:
        return f"Could not format the proposal: {error}"


format_lunch_proposal_tool = FunctionTool(format_lunch_proposal)
