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

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
import pytest

from app.agent import synthesizer_agent
from app.proposal_builder import (
    ROLE_DESCRIPTION,
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

SAMPLE_MENUS: list[dict[str, Any]] = [
    {
        "menu_id": "menu_1",
        "theme_name": "Baja Fiesta",
        "mains": [
            {"name": "Carnitas Taco Platter", "description": "Slow-cooked pork carnitas tacos"},
            {"name": "Vegan Sweet Potato Enchiladas", "description": "Corn tortillas with black beans"},
        ],
        "sides": [
            {"name": "Southwest Roasted Corn & Black Bean Salad"},
            {"name": "Guacamole & Tortilla Chips"},
        ],
        "beverages": [
            {"name": "Mexican Horchata"},
        ],
        "desserts": [
            {"name": "Churro Bites with Dulce de Leche"},
        ],
    },
    {
        "menu_id": "menu_2",
        "theme_name": "Mediterranean Delight",
        "mains": [
            {"name": "Chicken Shawarma Plate", "description": "Spiced chicken with garlic sauce"},
            {"name": "Veggie Mezze Platter Main", "description": "Hummus, falafel, dolmas"},
        ],
        "sides": [
            {"name": "Greek Farmer Salad"},
            {"name": "Hummus & Warm Pita Chips"},
        ],
        "beverages": [
            {"name": "Cucumber Mint Detox Water"},
        ],
        "desserts": [
            {"name": "Mini Cannoli Trio"},
        ],
    },
    {
        "menu_id": "menu_3",
        "theme_name": "Pan-Asian Bistro",
        "mains": [
            {"name": "Thai Red Curry Chicken", "description": "Red coconut curry with vegetables"},
            {"name": "Vegetable Fried Rice with Crispy Tofu", "description": "Fried rice with crispy tofu"},
        ],
        "sides": [
            {"name": "Asian Sesame Crunchy Slaw"},
            {"name": "Vegetable Spring Rolls"},
        ],
        "beverages": [
            {"name": "Matcha Green Tea Iced Latte"},
        ],
        "desserts": [
            {"name": "Coconut Mango Rice Pudding"},
        ],
    },
]


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


def test_build_lunch_proposal_markdown_basic_with_catering_and_accommodations() -> None:
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
        catering_menus=SAMPLE_MENUS,
        accommodations="Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)",
    )

    # Core proposal structure
    assert "# OmniChef Launch Lunch" in markdown
    assert "**Strategic Rationale**: Aligns cross-functional team on Q4 launch goals." in markdown
    assert "Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in markdown
    assert "1. **Tue 12 Aug, 12:00-13:00 (8 of 8 free)** ⭐ *Recommended*" in markdown
    assert "*Absences*: Everyone can attend" in markdown
    assert "2. **Wed 13 Aug, 12:30-13:30 (7 of 8 free)**" in markdown
    assert "*Absences*: Kai" in markdown

    # Proposed Catering Menus: 3 thematic menus
    assert "Proposed Catering Menus" in markdown
    assert "Baja Fiesta" in markdown
    assert "Mediterranean Delight" in markdown
    assert "Pan-Asian Bistro" in markdown

    # 4-course items represented
    assert "Carnitas Taco Platter" in markdown
    assert "Southwest Roasted Corn & Black Bean Salad" in markdown
    assert "Mexican Horchata" in markdown
    assert "Churro Bites with Dulce de Leche" in markdown
    assert "Chicken Shawarma Plate" in markdown
    assert "Greek Farmer Salad" in markdown
    assert "Cucumber Mint Detox Water" in markdown
    assert "Mini Cannoli Trio" in markdown
    assert "Thai Red Curry Chicken" in markdown
    assert "Asian Sesame Crunchy Slaw" in markdown
    assert "Matcha Green Tea Iced Latte" in markdown
    assert "Coconut Mango Rice Pudding" in markdown

    # Dietary Accommodations prominent display
    assert "Dietary Accommodations" in markdown
    assert "Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)" in markdown

    # Obsolete placeholder completely replaced
    assert "You might want to order some food for this meeting." not in markdown
    assert "*To confirm, reply with your preferred time slot" in markdown


def test_build_lunch_proposal_markdown_without_accommodations() -> None:
    slots = [
        {"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""},
    ]
    markdown = build_lunch_proposal_markdown(
        title="OmniChef Launch Lunch",
        rationale="Aligns cross-functional team on Q4 launch goals.",
        attendees=SAMPLE_ROSTER,
        time_slots=slots,
        recommended_slot="2026-08-12T12:00",
        catering_menus=SAMPLE_MENUS,
        accommodations="",
    )

    assert "Proposed Catering Menus" in markdown
    assert "Baja Fiesta" in markdown
    assert "Mediterranean Delight" in markdown
    assert "Pan-Asian Bistro" in markdown
    assert "Filtered to accommodate" not in markdown
    assert "You might want to order some food for this meeting." not in markdown


def test_build_lunch_proposal_markdown_slot_validation_errors() -> None:
    with pytest.raises(ValueError, match="at least one time slot is required"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=[],
            recommended_slot="2026-08-12T12:00",
            catering_menus=SAMPLE_MENUS,
        )

    with pytest.raises(ValueError, match="recommended_slot 'invalid' is not one of the offered slots"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=[{"label": "Slot 1", "value": "2026-08-12T12:00", "absent": ""}],
            recommended_slot="invalid",
            catering_menus=SAMPLE_MENUS,
        )


@pytest.mark.parametrize("fewer_menus", [
    [],
    SAMPLE_MENUS[:1],
    SAMPLE_MENUS[:2],
])
def test_build_lunch_proposal_markdown_fewer_than_three_menus(fewer_menus: list[dict[str, Any]]) -> None:
    slots = [{"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""}]
    with pytest.raises(ValueError, match="(?i)(3|three).*menu|menu"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=slots,
            recommended_slot=SAMPLE_VALUES[0],
            catering_menus=fewer_menus,
        )


def test_build_lunch_proposal_markdown_more_than_three_menus() -> None:
    slots = [{"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""}]
    four_menus = SAMPLE_MENUS + [SAMPLE_MENUS[0]]
    with pytest.raises(ValueError, match="(?i)(3|three).*menu|menu"):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=slots,
            recommended_slot=SAMPLE_VALUES[0],
            catering_menus=four_menus,
        )


def test_build_lunch_proposal_markdown_malformed_missing_theme_name() -> None:
    slots = [{"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""}]
    malformed = [
        {
            "mains": [{"name": "M"}],
            "sides": [{"name": "S1"}, {"name": "S2"}],
            "beverages": [{"name": "B"}],
            "desserts": [{"name": "D"}],
        },
        SAMPLE_MENUS[1],
        SAMPLE_MENUS[2],
    ]
    with pytest.raises(ValueError):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=slots,
            recommended_slot=SAMPLE_VALUES[0],
            catering_menus=malformed,
        )


@pytest.mark.parametrize("course", ["mains", "sides", "beverages", "desserts"])
def test_build_lunch_proposal_markdown_malformed_missing_course(course: str) -> None:
    slots = [{"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""}]
    bad_menu = {k: v for k, v in SAMPLE_MENUS[0].items() if k != course}
    malformed = [bad_menu, SAMPLE_MENUS[1], SAMPLE_MENUS[2]]
    with pytest.raises(ValueError):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=slots,
            recommended_slot=SAMPLE_VALUES[0],
            catering_menus=malformed,
        )


@pytest.mark.parametrize("course", ["mains", "sides", "beverages", "desserts"])
def test_build_lunch_proposal_markdown_malformed_empty_course(course: str) -> None:
    slots = [{"label": SAMPLE_LABELS[0], "value": SAMPLE_VALUES[0], "absent": ""}]
    bad_menu = {**SAMPLE_MENUS[0], course: []}
    malformed = [bad_menu, SAMPLE_MENUS[1], SAMPLE_MENUS[2]]
    with pytest.raises(ValueError):
        build_lunch_proposal_markdown(
            title="Title",
            rationale="Rationale",
            attendees=SAMPLE_ROSTER,
            time_slots=slots,
            recommended_slot=SAMPLE_VALUES[0],
            catering_menus=malformed,
        )


def _mock_tool_context(scheduling_agent_output: str) -> MagicMock:
    tool_context = MagicMock()
    tool_context.invocation_id = "inv-123"

    event = MagicMock()
    event.author = "scheduling_agent"
    event.invocation_id = "inv-123"
    part = MagicMock()
    part.text = scheduling_agent_output
    event.content.parts = [part]

    tool_context.session.events = [event]
    return tool_context


def test_format_lunch_proposal_success() -> None:
    ctx = _mock_tool_context(
        "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai\n"
        "1. Tue 12 Aug, 12:00-13:00 - 8 of 8 free\n"
    )

    result = format_lunch_proposal(
        title="OmniChef Alignment",
        rationale="Align on milestones.",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        catering_menus=SAMPLE_MENUS,
        accommodations="Filtered to accommodate: Peanut allergy (Alice)",
        tool_context=ctx,
    )

    assert "# OmniChef Alignment" in result
    assert "### Included Team Members" in result
    assert "Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai" in result
    assert "Baja Fiesta" in result
    assert "Mediterranean Delight" in result
    assert "Pan-Asian Bistro" in result
    assert "Filtered to accommodate: Peanut allergy (Alice)" in result
    assert "You might want to order some food for this meeting." not in result


def test_format_lunch_proposal_without_accommodations() -> None:
    ctx = _mock_tool_context(
        "Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai\n"
        "1. Tue 12 Aug, 12:00-13:00 - 8 of 8 free\n"
    )

    result = format_lunch_proposal(
        title="OmniChef Alignment",
        rationale="Align on milestones.",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        catering_menus=SAMPLE_MENUS,
        accommodations="",
        tool_context=ctx,
    )

    assert "# OmniChef Alignment" in result
    assert "Baja Fiesta" in result
    assert "Filtered to accommodate" not in result
    assert "You might want to order some food for this meeting." not in result


def test_format_lunch_proposal_invalid_catering_menus() -> None:
    ctx = _mock_tool_context("Team (8): Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai")
    result = format_lunch_proposal(
        title="Title",
        rationale="Rationale",
        attendees=SAMPLE_ROSTER,
        slot_labels=SAMPLE_LABELS,
        slot_values=SAMPLE_VALUES,
        slot_absentees=SAMPLE_ABSENT,
        recommended_slot=SAMPLE_VALUES[0],
        catering_menus=SAMPLE_MENUS[:2],  # Fewer than 3 menus
        tool_context=ctx,
    )
    assert result.startswith("Could not format the proposal:")


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
        catering_menus=SAMPLE_MENUS,
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
        catering_menus=SAMPLE_MENUS,
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
        catering_menus=SAMPLE_MENUS,
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
        catering_menus=SAMPLE_MENUS,
        tool_context=ctx,
    )
    assert "slot_absentees names people who are not on the team: Bob" in result


def test_synthesizer_prompt_booking_turn_catering_menu() -> None:
    """Verifies synthesizer instruction instructs model to capture catering menu on booking."""
    instruction = str(synthesizer_agent.instruction) if synthesizer_agent.instruction else ROLE_DESCRIPTION

    # Booking confirmation bullets must include Catering Menu and exclude obsolete Food Reminder
    assert "Catering Menu" in instruction
    assert "Food Reminder" not in instruction
    assert "You might want to order some food for this meeting." not in instruction

    # Synthesizer instruction must mention catering context or menus
    assert "cater" in instruction.lower()
