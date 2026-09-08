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


def get_catering_menus() -> list[dict[str, Any]]:
    """Retrieves 3 distinct mock catering menu options for lunch meetings.

    Each menu contains 4 courses: Main, Side, Dessert, and Beverage.
    Executes in <1ms without any external database or network dependency.
    """
    return [dict(menu) for menu in MOCK_MENUS]
