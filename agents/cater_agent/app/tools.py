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

from typing import Any

MOCK_MENUS: list[dict[str, Any]] = [
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


def get_catering_menus() -> str:
    """Returns static mock catering menu suggestions for a team lunch meeting.

    Returns the 3 available mock menus without external network or database retrieval.
    """
    lines = [
        "### Catering Menu Options",
        "1. **Menu Option 1: Buffalo Chicken Wrap** (menu_id: menu_1)",
        "   * *Items*: buffalo chicken wrap, mixed greens salad, chocolate cookie, assorted sodas",
        "2. **Menu Option 2: Veggie Tacos** (menu_id: menu_2)",
        "   * *Items*: veggie tacos, snow pea salad, apple tartlets, tea service",
        "3. **Menu Option 3: Lamb Vindaloo** (menu_id: menu_3)",
        "   * *Items*: lamb vindaloo, spiced cauliflower, naan, orange-mint spa water",
    ]
    return "\n".join(lines)
