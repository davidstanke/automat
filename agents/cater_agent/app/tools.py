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

"""Tools for the Catering Agent.

Exposes ADK tools for:
- Recording individual and team dietary preferences/allergies in persistent memory.
- Retrieving active dietary preferences.
- Generating exactly 3 curated 4-course thematic catering menus filtered for dietary safety.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import dietary_preferences, menu_service

logger = logging.getLogger(__name__)

# Predefined culinary themes with preferred items and keywords
THEME_DEFINITIONS: list[dict[str, Any]] = [
    {
        "menu_id": "menu_1",
        "theme_name": "Baja Fiesta",
        "keywords": {
            "baja", "fiesta", "taco", "tacos", "enchilada", "enchiladas",
            "burrito", "quesadilla", "carnitas", "barbacoa", "fajita",
            "mexican", "horchata", "churro", "churros", "salsa",
            "guacamole", "plantains", "tostones", "chipotle",
        },
        "preferred_mains": [
            "Carnitas Taco Platter",
            "Vegan Sweet Potato Enchiladas",
            "Chicken Enchiladas Suizas",
            "Barbacoa Beef Burrito Bowl",
            "Fajita Chicken Bowl",
            "Grilled Mahi Mahi Tacos",
            "Cheese & Spinach Quesadilla",
            "Chile Relleno",
            "Birria Beef Tacos with Consomé",
            "Black Bean & Sweet Potato Burrito",
            "Grilled Steak Quesadilla",
            "Chipotle Steak Rice Bowl",
        ],
        "preferred_sides": [
            "Southwest Roasted Corn & Black Bean Salad",
            "Guacamole & Tortilla Chips",
            "Spanish Yellow Rice & Beans",
            "Fried Plantains (Tostones)",
            "Roasted Sweet Potato Wedges",
        ],
        "preferred_beverages": [
            "Mexican Horchata",
            "Hibiscus Sweet Tea",
            "Fresh Cold-Pressed Lemonade",
            "Sparkling Citrus Water",
        ],
        "preferred_desserts": [
            "Churro Bites with Dulce de Leche",
            "Fresh Fruit Skewer",
            "Gluten-Free Flourless Chocolate Cake",
        ],
    },
    {
        "menu_id": "menu_2",
        "theme_name": "Mediterranean Delight",
        "keywords": {
            "mediterranean", "greek", "shawarma", "gyro", "souvlaki",
            "kebab", "kabob", "falafel", "mezze", "shakshuka", "spanakopita",
            "hummus", "tabbouleh", "couscous", "pita", "tzatziki", "cannoli",
            "macaron", "feta", "tagine",
        },
        "preferred_mains": [
            "Chicken Shawarma Plate",
            "Veggie Mezze Platter Main",
            "Greek Chicken Souvlaki",
            "Vegan Falafel Pita Box",
            "Chicken Kabob Skewers",
            "Kofta Beef Kebab Bowl",
            "Beef & Lamb Gyro Platter",
            "Shakshuka with Pita",
            "Spanakopita Meal",
            "Grilled Salmon Mediterranean Bowl",
            "Mediterranean Chicken Gyro Box",
            "Grilled Veggie & Hummus Wrap",
            "Caprese Focaccia Panini",
        ],
        "preferred_sides": [
            "Greek Farmer Salad",
            "Hummus & Warm Pita Chips",
            "Mediterranean Couscous Salad",
            "Tabbouleh Salad",
            "Orzo Spinach & Feta Salad",
            "Watermelon Feta Mint Salad",
            "Quinoa & Roasted Veggie Salad",
        ],
        "preferred_beverages": [
            "Cucumber Mint Detox Water",
            "Fresh Cold-Pressed Lemonade",
            "Sparkling Citrus Water",
            "Iced Black Tea (Unsweetened)",
        ],
        "preferred_desserts": [
            "Mini Cannoli Trio",
            "Fresh Fruit Skewer",
            "Assorted Macaron Trio",
            "Vegan Chocolate Avocado Mousse",
        ],
    },
    {
        "menu_id": "menu_3",
        "theme_name": "Pan-Asian Bistro",
        "keywords": {
            "asian", "bistro", "teriyaki", "curry", "tofu", "fried rice",
            "lo mein", "noodles", "pad thai", "miso", "bulgogi", "singapore",
            "mongolian", "spring rolls", "edamame", "slaw", "matcha",
            "mango lassi", "rice pudding",
        },
        "preferred_mains": [
            "Thai Red Curry Chicken",
            "Vegetable Fried Rice with Crispy Tofu",
            "Chicken Teriyaki Bento Box",
            "General Tso's Tofu",
            "Beef & Broccoli Stir Fry",
            "Miso Glazed Salmon",
            "Sweet & Sour Chicken",
            "Orange Chicken Plate",
            "Sesame Ginger Tofu & Noodle Bowl",
            "Chicken Lo Mein Noodles",
            "Mongolian Beef",
            "Singapore Street Noodles",
            "Korean BBQ Beef Bulgogi Bowl",
        ],
        "preferred_sides": [
            "Asian Sesame Crunchy Slaw",
            "Vegetable Spring Rolls",
            "Steamed Garlic Broccoli",
            "Garlic Herb Roasted Potatoes",
        ],
        "preferred_beverages": [
            "Matcha Green Tea Iced Latte",
            "Iced Black Tea (Unsweetened)",
            "Ginger Beer (Non-Alcoholic)",
            "Cold Brew Coffee",
            "Bottled Spring Water",
        ],
        "preferred_desserts": [
            "Coconut Mango Rice Pudding",
            "Fresh Fruit Skewer",
            "Vegan Chocolate Avocado Mousse",
        ],
    },
]


def _format_item(item: dict[str, Any]) -> dict[str, Any]:
    """Formats a menu item dict conforming to the ThematicMenu schema."""
    return {
        "name": str(item.get("name", "")).strip(),
        "description": str(item.get("description", "")).strip(),
        "allergens": list(item.get("allergens", [])),
        "dietary_labels": list(item.get("dietary_labels", [])),
    }


def _pick_course_items(
    theme_def: dict[str, Any],
    course: str,
    safe_items: list[dict[str, Any]],
    target_count: int,
    min_count: int,
    max_count: int,
    already_used_names: set[str],
) -> list[dict[str, Any]]:
    """Selects safe items for a given course matching theme preferences or keywords."""
    preferred_names = theme_def.get(f"preferred_{course}", [])
    keywords = theme_def.get("keywords", set())

    safe_by_name = {item["name"].strip().lower(): item for item in safe_items}
    chosen_items: list[dict[str, Any]] = []
    chosen_names: set[str] = set()

    # Pass 1: Preferred items not yet used in earlier menus
    for pref_name in preferred_names:
        key = pref_name.strip().lower()
        if key in safe_by_name and key not in already_used_names and key not in chosen_names:
            chosen_items.append(safe_by_name[key])
            chosen_names.add(key)
            if len(chosen_items) >= target_count:
                break

    # Pass 2: Preferred items even if used in an earlier menu (as long as unique within this menu)
    if len(chosen_items) < target_count:
        for pref_name in preferred_names:
            key = pref_name.strip().lower()
            if key in safe_by_name and key not in chosen_names:
                chosen_items.append(safe_by_name[key])
                chosen_names.add(key)
                if len(chosen_items) >= target_count:
                    break

    # Pass 3: Keyword matching items
    if len(chosen_items) < target_count:
        for item in safe_items:
            key = item["name"].strip().lower()
            if key in chosen_names:
                continue
            text = f"{item['name']} {item.get('description', '')}".lower()
            if any(kw in text for kw in keywords):
                chosen_items.append(item)
                chosen_names.add(key)
                if len(chosen_items) >= target_count:
                    break

    # Pass 4: Fallback to any remaining safe items
    if len(chosen_items) < min_count:
        for item in safe_items:
            key = item["name"].strip().lower()
            if key not in chosen_names:
                chosen_items.append(item)
                chosen_names.add(key)
                if len(chosen_items) >= min_count:
                    break

    # If still below min_count (e.g. only 1 side safe in total), pad to satisfy min_count
    if chosen_items and len(chosen_items) < min_count:
        while len(chosen_items) < min_count:
            chosen_items.append(chosen_items[0])

    final_items = chosen_items[:max_count]
    return [_format_item(item) for item in final_items]


async def record_dietary_preference(
    person_name: str,
    preference_type: str,
    details: str,
) -> str:
    """Records a team member's dietary preference, allergy, like, or dislike in persistent memory.

    Args:
        person_name: Name of the individual or 'team'.
        preference_type: Type of preference ('allergy', 'restriction', 'dislike', 'like').
        details: Details of the dietary item or constraint.

    Returns:
        Formatted confirmation message.
    """
    saved = await dietary_preferences.add_preference(
        person_name=person_name,
        preference_type=preference_type,
        details=details,
    )
    clean_name = saved.get("person_name", "")
    clean_details = saved.get("details", "")
    clean_type = saved.get("preference_type", "")
    return (
        f"Saved dietary preference for {clean_name}: {clean_details} {clean_type}. "
        "This will be applied to all future lunch recommendations."
    )


async def get_dietary_preferences() -> str:
    """Retrieves all active dietary preferences recorded for the team.

    Returns:
        Formatted summary of dietary preferences or a message indicating none are recorded.
    """
    prefs = await dietary_preferences.list_preferences()
    if not prefs:
        return "No dietary preferences recorded for the team."

    lines = ["Recorded dietary preferences:"]
    for pref in prefs:
        person = pref.get("person_name", "")
        pref_type = pref.get("preference_type", "")
        details = pref.get("details", "")
        lines.append(f"- {person}: {details} ({pref_type})")
    return "\n".join(lines)


async def get_thematic_menus() -> str:
    """Generates exactly 3 distinct curated 4-course thematic catering menus filtered by active dietary preferences.

    Retrieves recorded dietary preferences from memory, fetches menu items from BigQuery/local fallback,
    filters items for allergen/restriction safety, and structures exactly 3 themed menus (1-3 mains,
    2-3 sides, >=1 beverage, >=1 dessert).

    Returns:
        JSON string containing the list of 3 thematic menus and dietary accommodation notes.
    """
    prefs = await dietary_preferences.list_preferences()
    raw_items = await menu_service.query_menu_items()
    safe_items, applied_accommodations = menu_service.filter_items_by_preferences(raw_items, prefs)

    grouped_safe = menu_service.group_items_by_category(safe_items)
    safe_mains = grouped_safe.get("mains", [])
    safe_sides = grouped_safe.get("sides", [])
    safe_beverages = grouped_safe.get("beverages", [])
    safe_desserts = grouped_safe.get("desserts", [])

    menus: list[dict[str, Any]] = []
    used_item_names: set[str] = set()

    for theme_def in THEME_DEFINITIONS:
        mains = _pick_course_items(
            theme_def=theme_def,
            course="mains",
            safe_items=safe_mains,
            target_count=2,
            min_count=1,
            max_count=3,
            already_used_names=used_item_names,
        )
        sides = _pick_course_items(
            theme_def=theme_def,
            course="sides",
            safe_items=safe_sides,
            target_count=2,
            min_count=2,
            max_count=3,
            already_used_names=used_item_names,
        )
        beverages = _pick_course_items(
            theme_def=theme_def,
            course="beverages",
            safe_items=safe_beverages,
            target_count=1,
            min_count=1,
            max_count=2,
            already_used_names=used_item_names,
        )
        desserts = _pick_course_items(
            theme_def=theme_def,
            course="desserts",
            safe_items=safe_desserts,
            target_count=1,
            min_count=1,
            max_count=2,
            already_used_names=used_item_names,
        )

        for item in mains + sides + beverages + desserts:
            used_item_names.add(item["name"].strip().lower())

        menus.append({
            "menu_id": theme_def["menu_id"],
            "theme_name": theme_def["theme_name"],
            "mains": mains,
            "sides": sides,
            "beverages": beverages,
            "desserts": desserts,
        })

    accommodations_str = (
        f"Filtered to accommodate: {', '.join(applied_accommodations)}"
        if applied_accommodations
        else ""
    )

    result = {
        "menus": menus,
        "accommodations": accommodations_str,
    }

    return json.dumps(result, indent=2)


__all__ = [
    "get_dietary_preferences",
    "get_thematic_menus",
    "record_dietary_preference",
]
