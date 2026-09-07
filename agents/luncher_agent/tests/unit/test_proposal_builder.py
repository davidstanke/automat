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

from unittest.mock import MagicMock
import pytest

from app.proposal_builder import (
    _roster_from_text,
    _split_names,
    build_lunch_proposal_markdown,
    format_lunch_proposal,
)

SAMPLE_ROSTER = ["Liam", "Diego", "Dan", "Maya", "Aaliyah", "Naomi", "Jordan", "Kai"]
SAMPLE_LABELS = [
    "Tue 12 Aug, 12:00-13:00 (8 of 8 free)",
    "Wed 13 Aug, 12:30-13:30 (7 of 8 free)",
    "Thu 14 Aug, 12:00-13:00 (6 of 8 free)",
]
SAMPLE_VALUES = ["2026-08-12T12:00", "2026-08-13T12:30", "2026-08-14T12:00"]
SAMPLE_ABSENT = ["", "Kai", "Maya, Liam"]


def test_split_names() -> None:
    assert _split_names("Liam, Diego, Dan and Maya") == ["Liam", "Diego", "Dan", "Maya"]
    assert _split_names("Kai, Maya") == ["Kai", "Maya"]
    assert _split_names("  *Diego* , Dan. ") == ["Diego", "Dan"]


def test_roster_from_text() -> None:
    text = (
        "## Team Roster\n"
        "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai\n"
        "## Available Time Slots\n"
    )
    assert _roster_from_text(text) == SAMPLE_ROSTER

    text_no_roster = "Here are the times: Tuesday at 12."
    assert _roster_from_text(text_no_roster) is None


def test_build_lunch_proposal_markdown_basic() -> None:
    slots = [
        {"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""},
        {"label": SAMPLE_LABELS[1], "value": SAMPLE_VALUES[1], "absent": "Kai"},
    ]
    markdown = build_lunch_proposal_markdown(
        title="OmniChef Launch Lunch",
        rationale="Aligns cross-functional team on Q4 launch goals.",
        attendees=SAMPLE_ROSTER,
        time_slots=slots,
        recommended_slot="2026-08-12T12:00",
    )

    assert "# OmniChef Launch Lunch" in markdown
    assert "**Strategic Rationale**: Aligns cross-functional team on Q4 launch goals." in markdown
    assert "Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in markdown
    assert "1. **Tue 12 Aug, 12:00-13:00 (8 of 8 free)** ⭐ *Recommended*" in markdown
    assert "*Absences*: Everyone can attend" in markdown
    assert "2. **Wed 13 Aug, 12:30-13:30 (7 of 8 free)**" in markdown
    assert "*Absences*: Kai" in markdown
    assert "### Catering Menu Options" in markdown
    assert "Menu Option 1: Buffalo Chicken Wrap" in markdown
    assert "Menu Option 2: Veggie Tacos" in markdown
    assert "Menu Option 3: Lamb Vindaloo" in markdown
    assert "*To confirm, reply with your preferred time slot and catering menu" in markdown


def test_build_lunch_proposal_markdown_catering_unavailable() -> None:
    slots = [
        {"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""},
    ]
    markdown = build_lunch_proposal_markdown(
        title="OmniChef Launch Lunch",
        rationale="Aligns cross-functional team on Q4 launch goals.",
        attendees=SAMPLE_ROSTER,
        time_slots=slots,
        recommended_slot="2026-08-12T12:00",
        catering_unavailable=True,
    )

    assert "### Catering Menu Options" in markdown
    assert "*Catering menu suggestions are temporarily unavailable.*" in markdown


def test_build_lunch_proposal_markdown_validation_errors() -> None:
    with pytest.raises(ValueError, match="at least one time slot is required"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=[],
            recommended_slot="2026-08-12T12:00",
        )

    with pytest.raises(ValueError, match="recommended_slot 'invalid' is not one of the offered slots"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=[{"label": "Slot 1", "value": "2026-08-12T12:00", "absent": ""}],
            recommended_slot="invalid",
        )


def _mock_tool_context(scheduling_agent_output: str, cater_agent_output: str = "") -> MagicMock:
    tool_context = MagicMock()
    tool_context.invocation_id = "inv-123"

    events = []
    event_sched = MagicMock()
    event_sched.author = "scheduling_agent"
    event_sched.invocation_id = "inv-123"
    part_sched = MagicMock()
    part_sched.text = scheduling_agent_output
    event_sched.content.parts = [part_sched]
    events.append(event_sched)

    if cater_agent_output:
        event_cater = MagicMock()
        event_cater.author = "cater_agent"
        event_cater.invocation_id = "inv-123"
        part_cater = MagicMock()
        part_cater.text = cater_agent_output
        event_cater.content.parts = [part_cater]
        events.append(event_cater)

    tool_context.session.events = events
    return tool_context


def test_format_lunch_proposal_success() -> None:
    ctx = _mock_tool_context(
        "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai\n"
        "1. Tue 12 Aug, 12:00-13:00 - 8 of 8 free\n",
        "### Catering Menu Options\n1. Menu Option 1: Buffalo Chicken Wrap",
    )

    result = format_lunch_proposal(
        title="OmniChef Alignment",
        rationale="Align on milestones.",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        tool_context=ctx,
    )

    assert "# OmniChef Alignment" in result
    assert "### Included Team Members" in result
    assert "Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in result
    assert "### Catering Menu Options" in result
    assert "Buffalo Chicken Wrap" in result


def test_format_lunch_proposal_mismatched_lengths() -> None:
    ctx = _mock_tool_context("Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai")
    result = format_lunch_proposal(
        title="Title",
        rationale="Rationale",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES[:1],  # Mismatched length
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        tool_context=ctx,
    )
    assert "Could not format the proposal: slot_labels has 3 entries but slot_values has 1" in result


def test_format_lunch_proposal_missing_attendee() -> None:
    ctx = _mock_tool_context("Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai")
    result = format_lunch_proposal(
        title="Title",
        rationale="Rationale",
        attendees=SAMPLE_ROSTER[:7],  # Missing Kai
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        tool_context=ctx,
    )
    assert "Could not format the proposal: attendees must be exactly the team the scheduling agent named" in result
    assert "missing Kai" in result


def test_format_lunch_proposal_extra_attendee() -> None:
    ctx = _mock_tool_context("Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai")
    result = format_lunch_proposal(
        title="Title",
        rationale="Rationale",
        attendees=SAMPLE_ROSTER + ["Alice"],  # Extra Alice
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        tool_context=ctx,
    )
    assert "Could not format the proposal: attendees must be exactly the team the scheduling agent named" in result
    assert "not on the team: Alice" in result


def test_format_lunch_proposal_invalid_absentee() -> None:
    ctx = _mock_tool_context("Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai")
    result = format_lunch_proposal(
        title="Title",
        rationale="Rationale",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=["", "Bob", ""],  # Bob not on roster
        recommended_slot=SAMPLE_VALUES[0],
        tool_context=ctx,
    )
    assert "slot_absentees names people who are not on the team: Bob" in result
