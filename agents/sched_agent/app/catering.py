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

"""Catering menu constants and conversational matching helper for scheduling."""

from __future__ import annotations

import re
from typing import Any

MOCK_CATERING_MENUS: dict[str, dict[str, Any]] = {
    "menu_1": {
        "menu_id": "menu_1",
        "name": "Buffalo Chicken Wrap Platter",
        "items": [
            "buffalo chicken wrap",
            "mixed greens salad",
            "chocolate cookie",
            "assorted sodas",
        ],
    },
    "menu_2": {
        "menu_id": "menu_2",
        "name": "Veggie Taco Fiesta",
        "items": [
            "veggie tacos",
            "snow pea salad",
            "apple tartlets",
            "tea service",
        ],
    },
    "menu_3": {
        "menu_id": "menu_3",
        "name": "Indian Curry Feast",
        "items": [
            "lamb vindaloo",
            "spiced cauliflower",
            "naan",
            "orange-mint spa water",
        ],
    },
}

DEFAULT_CATERING_MENU = MOCK_CATERING_MENUS["menu_1"]


def normalize_catering_choice(
    choice: str | None,
) -> tuple[dict[str, Any], bool, str | None]:
    """Resolves and normalizes a catering menu selection.

    Args:
        choice: Raw string input from user or agent (e.g. 'menu_2', 'Veggie Tacos', 'the taco platter', '').

    Returns:
        tuple of (selected_menu_dict, is_default, warning_message_or_None)
    """
    if not choice or not choice.strip():
        return DEFAULT_CATERING_MENU, True, None

    clean = choice.lower().strip()

    # Direct canonical and synonym checks
    if clean in (
        "menu_1",
        "menu 1",
        "option 1",
        "choice 1",
        "1",
        "buffalo chicken",
        "buffalo chicken wrap",
        "buffalo chicken wrap platter",
        "chicken wrap",
        "wrap platter",
        "buffalo wrap",
    ):
        return MOCK_CATERING_MENUS["menu_1"], False, None

    if clean in (
        "menu_2",
        "menu 2",
        "option 2",
        "choice 2",
        "2",
        "veggie taco",
        "veggie tacos",
        "veggie taco fiesta",
        "taco fiesta",
        "tacos",
        "the taco platter",
        "the taco option",
        "veggie taco option",
        "taco platter",
    ):
        return MOCK_CATERING_MENUS["menu_2"], False, None

    if clean in (
        "menu_3",
        "menu 3",
        "option 3",
        "choice 3",
        "3",
        "indian curry",
        "indian curry feast",
        "curry feast",
        "lamb vindaloo",
        "curry",
        "vindaloo",
    ):
        return MOCK_CATERING_MENUS["menu_3"], False, None

    # Regex keyword matching
    if re.search(r"\b(menu\s*2|option\s*2|veggie\s*taco|taco|fiesta)\b", clean):
        return MOCK_CATERING_MENUS["menu_2"], False, None
    if re.search(r"\b(menu\s*3|option\s*3|indian\s*curry|curry|vindaloo|lamb)\b", clean):
        return MOCK_CATERING_MENUS["menu_3"], False, None
    if re.search(r"\b(menu\s*1|option\s*1|buffalo|chicken\s*wrap|wrap)\b", clean):
        return MOCK_CATERING_MENUS["menu_1"], False, None

    # Unrecognized menu choice -> Fallback to menu_1 with warning (AC6)
    warning = f"Selected catering menu '{choice}' was unrecognized. Defaulted to Menu Option 1 ({DEFAULT_CATERING_MENU['name']})."
    return DEFAULT_CATERING_MENU, False, warning
