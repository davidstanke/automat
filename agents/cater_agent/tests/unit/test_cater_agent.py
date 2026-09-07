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

"""Unit tests for the Catering Agent (cater_agent)."""

from app.models import CaterAgentResponse, CateringMenu
from app.tools import (
    MOCK_MENUS_DATA,
    get_catering_menus,
    get_mock_menus,
    get_mock_response,
)


def test_mock_menus_count_and_ids() -> None:
    """AC1: cater_agent returns exactly 3 mock menu suggestions."""
    menus = get_mock_menus()
    assert len(menus) == 3
    menu_ids = [m.menu_id for m in menus]
    assert menu_ids == ["menu_1", "menu_2", "menu_3"]


def test_mock_menus_content_and_items() -> None:
    """AC1: Verifies exact titles and courses for all 3 curated mock menus."""
    menus = {m.menu_id: m for m in get_mock_menus()}

    # Menu 1
    m1 = menus["menu_1"]
    assert m1.name == "Buffalo Chicken Wrap Platter"
    assert m1.items == [
        "buffalo chicken wrap",
        "mixed greens salad",
        "chocolate cookie",
        "assorted sodas",
    ]

    # Menu 2
    m2 = menus["menu_2"]
    assert m2.name == "Veggie Taco Fiesta"
    assert m2.items == [
        "veggie tacos",
        "snow pea salad",
        "apple tartlets",
        "tea service",
    ]

    # Menu 3
    m3 = menus["menu_3"]
    assert m3.name == "Indian Curry Feast"
    assert m3.items == [
        "lamb vindaloo",
        "spiced cauliflower",
        "naan",
        "orange-mint spa water",
    ]


def test_cater_agent_response_schema() -> None:
    """Verifies schema validation for CaterAgentResponse contract."""
    response = get_mock_response()
    assert isinstance(response, CaterAgentResponse)
    assert len(response.menus) == 3
    dumped = response.model_dump()
    assert "menus" in dumped
    assert len(dumped["menus"]) == 3


def test_get_catering_menus_tool_output() -> None:
    """Verifies tool output formatting and Markdown structure."""
    output = get_catering_menus()
    assert "### Catering Menu Options" in output
    assert "Buffalo Chicken Wrap Platter" in output
    assert "Veggie Taco Fiesta" in output
    assert "Indian Curry Feast" in output
    assert "buffalo chicken wrap" in output
    assert "tea service" in output
    assert "orange-mint spa water" in output
