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

"""Tools and mock data for the in-house catering agent."""

from typing import Any
from .models import CateringMenu, CaterAgentResponse

MOCK_MENUS_DATA: list[dict[str, Any]] = [
    {
        "menu_id": "menu_1",
        "name": "Buffalo Chicken Wrap Platter",
        "items": [
            "buffalo chicken wrap",
            "mixed greens salad",
            "chocolate cookie",
            "assorted sodas",
        ],
    },
    {
        "menu_id": "menu_2",
        "name": "Veggie Taco Fiesta",
        "items": [
            "veggie tacos",
            "snow pea salad",
            "apple tartlets",
            "tea service",
        ],
    },
    {
        "menu_id": "menu_3",
        "name": "Indian Curry Feast",
        "items": [
            "lamb vindaloo",
            "spiced cauliflower",
            "naan",
            "orange-mint spa water",
        ],
    },
]


def get_mock_menus() -> list[CateringMenu]:
    """Returns the validated list of 3 mock catering menus."""
    return [CateringMenu.model_validate(m) for m in MOCK_MENUS_DATA]


def get_mock_response() -> CaterAgentResponse:
    """Returns the full CaterAgentResponse object."""
    return CaterAgentResponse(menus=get_mock_menus())


def get_catering_menus() -> str:
    """Returns the 3 curated in-house catering menu options.

    Proposes 3 curated mock menus sourced from the company's in-house catering
    service without performing any external database or inventory retrieval.
    """
    print("[Catering Agent] Fetching curated in-house catering menus...")
    output_lines = ["### Catering Menu Options"]
    for idx, menu in enumerate(MOCK_MENUS_DATA, 1):
        items_str = ", ".join(menu["items"])
        output_lines.append(
            f"{idx}. **Menu {idx}: {menu['name']}** (`{menu['menu_id']}`)\n"
            f"   * *Items*: {items_str}"
        )
    return "\n".join(output_lines)
