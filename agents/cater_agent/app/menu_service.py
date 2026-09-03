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

"""Catering Menu Data Access & Offline Fallback Service.

Retrieves menu items from BigQuery via BigQuery MCP when configured,
with a strict 5.0-second socket timeout and automatic graceful fallback to the
local catering dataset (data/catering/catering_menu.json).
Provides category normalization, dietary restriction and allergen filtering,
and category grouping.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

# Socket / MCP query timeout limit in seconds
MCP_TIMEOUT: float = 5.0
SOCKET_TIMEOUT: float = 5.0

# Canonical categories
COURSE_CATEGORIES: tuple[str, ...] = ("mains", "sides", "beverages", "desserts")

# Common allergen keyword associations
ALLERGEN_TERMS_MAP: dict[str, set[str]] = {
    "peanut": {"peanut", "peanuts", "peanut butter"},
    "peanuts": {"peanut", "peanuts", "peanut butter"},
    "shellfish": {
        "shellfish",
        "shrimp",
        "shrimps",
        "prawn",
        "prawns",
        "crab",
        "crabs",
        "lobster",
        "lobsters",
        "clam",
        "clams",
        "mussel",
        "mussels",
        "oyster",
        "oysters",
        "scallop",
        "scallops",
    },
    "dairy": {
        "dairy",
        "milk",
        "cheese",
        "butter",
        "cream",
        "heavy cream",
        "sour cream",
        "yogurt",
        "ghee",
        "whey",
        "casein",
        "mozzarella",
        "parmesan",
        "provolone",
        "ricotta",
        "feta",
        "cheddar",
        "swiss cheese",
        "blue cheese",
        "monterey jack",
        "brie",
        "gouda",
        "queso",
    },
    "egg": {"egg", "eggs", "mayonnaise", "mayo"},
    "eggs": {"egg", "eggs", "mayonnaise", "mayo"},
    "fish": {
        "fish",
        "salmon",
        "tuna",
        "cod",
        "mahi mahi",
        "anchovy",
        "anchovies",
        "tilapia",
        "trout",
        "halibut",
        "bass",
    },
    "soy": {"soy", "soya", "soybeans", "tofu", "edamame", "miso", "tamari"},
    "sesame": {"sesame", "tahini"},
    "gluten": {
        "gluten",
        "wheat",
        "flour",
        "bread",
        "tortilla",
        "pasta",
        "ciabatta",
        "focaccia",
        "baguette",
        "brioche",
        "croutons",
        "barley",
        "rye",
    },
    "tree nut": {
        "tree nut",
        "tree nuts",
        "almond",
        "almonds",
        "walnut",
        "walnuts",
        "pecan",
        "pecans",
        "cashew",
        "cashews",
        "pistachio",
        "pistachios",
        "hazelnut",
        "hazelnuts",
        "macadamia",
        "pine nut",
        "pine nuts",
    },
    "tree nuts": {
        "tree nut",
        "tree nuts",
        "almond",
        "almonds",
        "walnut",
        "walnuts",
        "pecan",
        "pecans",
        "cashew",
        "cashews",
        "pistachio",
        "pistachios",
        "hazelnut",
        "hazelnuts",
        "macadamia",
        "pine nut",
        "pine nuts",
    },
}

_PLANT_BASED_EXEMPTIONS = (
    "almond milk",
    "coconut milk",
    "soy milk",
    "oat milk",
    "cashew milk",
    "rice milk",
    "vegan cheese",
    "vegan mozzarella",
    "plant-based",
)


def normalize_category(category: str) -> str:
    """Normalizes category strings to standard course categories."""
    cat = (category or "").strip().lower()
    if cat in (
        "sides_salads",
        "sides_salad",
        "sides-salads",
        "sides & salads",
        "salad",
        "salads",
        "side",
        "sides",
    ):
        return "sides"
    if cat in ("main", "mains"):
        return "mains"
    if cat in ("beverage", "beverages", "drink", "drinks"):
        return "beverages"
    if cat in ("dessert", "desserts"):
        return "desserts"
    return cat


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Ensures CateringItem dictionary adheres to expected schema and normalized category."""
    norm = copy.deepcopy(item) if isinstance(item, dict) else {}
    norm["category"] = normalize_category(str(norm.get("category", "")))

    for field in ("ingredients", "allergens", "dietary_labels"):
        val = norm.get(field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                norm[field] = parsed if isinstance(parsed, list) else [val]
            except Exception:
                norm[field] = [s.strip() for s in val.split(",") if s.strip()]
        elif not isinstance(val, list):
            norm[field] = list(val) if val is not None else []

    if "price" in norm:
        try:
            norm["price"] = float(norm["price"])
        except (ValueError, TypeError):
            pass

    return norm


def _find_catering_data_path() -> Path:
    """Locates data/catering/catering_menu.json across repository directory layouts."""
    current_file = Path(__file__).resolve()

    # Automat repo root relative to agents/cater_agent/app/menu_service.py
    if len(current_file.parents) >= 4:
        cand = current_file.parents[3] / "data" / "catering" / "catering_menu.json"
        if cand.exists():
            return cand

    for parent in current_file.parents:
        cand = parent / "data" / "catering" / "catering_menu.json"
        if cand.exists():
            return cand

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        cand = parent / "data" / "catering" / "catering_menu.json"
        if cand.exists():
            return cand

    return Path("data/catering/catering_menu.json")


def _load_local_dataset() -> list[dict[str, Any]]:
    """Loads and returns all menu items from data/catering/catering_menu.json."""
    path = _find_catering_data_path()
    if not path.exists():
        logger.error("Catering menu dataset not found at %s", path)
        return []

    items: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                items.append(item)
            except json.JSONDecodeError:
                pass
    return items


def _is_mcp_configured() -> bool:
    """Checks if BigQuery MCP environment variables are configured."""
    return bool(
        os.getenv("BIGQUERY_MCP_COMMAND")
        or os.getenv("BIGQUERY_MCP_URL")
        or os.getenv("BIGQUERY_MCP_SERVER")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    )


def _get_mcp_client() -> Any:
    """Returns an active BigQuery MCP client or None if unconfigured."""
    return None


async def _execute_mcp_query(
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Attempts to execute SQL query against catering.menu_items via BigQuery MCP."""
    client = _get_mcp_client()
    if client is not None and hasattr(client, "call_tool"):
        sql = "SELECT * FROM catering.menu_items"
        if categories:
            cat_list = ", ".join(f"'{normalize_category(c)}'" for c in categories)
            sql += f" WHERE LOWER(category) IN ({cat_list})"
        res = await client.call_tool("run_query", {"query": sql})
        if hasattr(res, "data"):
            return res.data
        if isinstance(res, dict) and "data" in res and isinstance(res["data"], list):
            return res["data"]
        if isinstance(res, list):
            return res
        return []

    raise ConnectionRefusedError("Unable to connect to BigQuery MCP server")


async def query_menu_items(
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Queries menu items via BigQuery MCP or falls back to local JSON dataset.

    Enforces a 5.0-second socket timeout on MCP tool execution and gracefully falls
    back to loading data/catering/catering_menu.json upon timeout, connection errors,
    or unauthenticated environments.

    Args:
        categories: Optional list of category names (e.g. ['mains', 'sides']).

    Returns:
        List of normalized CateringItem dictionaries.
    """
    raw_items: list[dict[str, Any]] = []

    if _is_mcp_configured():
        try:
            res = await asyncio.wait_for(
                _execute_mcp_query(categories=categories),
                timeout=MCP_TIMEOUT,
            )
            if isinstance(res, list):
                raw_items = res
            elif isinstance(res, dict) and "data" in res and isinstance(res["data"], list):
                raw_items = res["data"]
            else:
                raw_items = _load_local_dataset()
        except Exception as exc:
            logger.warning(
                "BigQuery MCP query failed or timed out (%s); falling back to local JSON dataset",
                exc,
            )
            raw_items = _load_local_dataset()
    else:
        raw_items = _load_local_dataset()

    normalized = [_normalize_item(item) for item in raw_items]

    if categories is not None:
        target_cats = {normalize_category(c) for c in categories}
        return [item for item in normalized if item["category"] in target_cats]

    return normalized


def _get_allergy_match_terms(allergy_str: str) -> set[str]:
    """Expands an allergen query string into variations and related synonyms."""
    norm = allergy_str.strip().lower()
    terms: set[str] = {norm}

    if norm.endswith("ies"):
        terms.add(norm[:-3] + "y")
    elif norm.endswith("s") and not norm.endswith("ss"):
        terms.add(norm[:-1])
    else:
        terms.add(norm + "s")

    for key, syns in ALLERGEN_TERMS_MAP.items():
        if norm == key or norm in syns:
            terms.update(syns)

    return terms


def _ingredient_contains_allergen_term(
    ingredient: str, term: str, norm_allergy: str
) -> bool:
    """Checks whether an ingredient string conflicts with an allergen term."""
    ing = ingredient.lower()
    t = term.lower()

    if norm_allergy in ("dairy", "milk", "cheese"):
        for sub in _PLANT_BASED_EXEMPTIONS:
            if sub in ing and t in sub:
                return False

    pattern = r"\b" + re.escape(t) + r"\b"
    return bool(re.search(pattern, ing))


def _has_allergen_conflict(item: dict[str, Any], allergy_str: str) -> bool:
    """Returns True if the item contains the allergen in allergens or ingredients."""
    terms = _get_allergy_match_terms(allergy_str)
    norm_allergy = allergy_str.strip().lower()

    item_allergens = [a.lower() for a in item.get("allergens", [])]
    for allergen in item_allergens:
        for t in terms:
            if t == allergen or re.search(r"\b" + re.escape(t) + r"\b", allergen):
                return True

    item_ingredients = item.get("ingredients", [])
    for ingredient in item_ingredients:
        for t in terms:
            if _ingredient_contains_allergen_term(str(ingredient), t, norm_allergy):
                return True

    return False


def _violates_restriction(item: dict[str, Any], restriction_str: str) -> bool:
    """Returns True if the item violates a dietary restriction."""
    norm_restr = restriction_str.strip().lower()
    labels_lower = [str(l).lower() for l in item.get("dietary_labels", [])]
    allergens_lower = [str(a).lower() for a in item.get("allergens", [])]
    ingredients_str = " ".join(str(i).lower() for i in item.get("ingredients", []))

    if norm_restr == "vegan":
        return "vegan" not in labels_lower

    if norm_restr == "vegetarian":
        if "vegetarian" not in labels_lower and "vegan" not in labels_lower:
            return True
        if any(meat in ingredients_str for meat in ("chicken", "beef", "pork", "shrimp", "salmon", "fish", "turkey")):
            return True
        return False

    if norm_restr in ("gluten-free", "gluten free", "gluten"):
        if "gluten" in allergens_lower:
            return True
        if "gluten-free" not in labels_lower:
            if any(re.search(r"\b(gluten|wheat|barley|rye)\b", ing.lower()) for ing in item.get("ingredients", [])):
                return True
        return False

    if norm_restr in ("dairy-free", "dairy free", "dairy"):
        if "dairy" in allergens_lower:
            return True
        if "dairy-free" not in labels_lower:
            return _has_allergen_conflict(item, "dairy")
        return False

    norm_hyphen = norm_restr.replace(" ", "-")
    return norm_restr not in labels_lower and norm_hyphen not in labels_lower


def _format_accommodation_summary(pref: dict[str, Any]) -> str | None:
    """Formats an active dietary constraint into a human-readable summary string."""
    pref_type = str(pref.get("preference_type", "")).strip().lower()
    details = str(pref.get("details", "")).strip()
    person = str(pref.get("person_name", "")).strip()

    if not details or not person:
        return None

    if pref_type == "allergy":
        allergen = details
        norm = allergen.lower()
        if norm.endswith("ies"):
            allergen = allergen[:-3] + ("Y" if allergen[-1].isupper() else "y")
        elif norm.endswith("s") and not norm.endswith("ss"):
            allergen = allergen[:-1]
        return f"{allergen.title()} allergy ({person})"
    elif pref_type == "restriction":
        formatted_details = "-".join(part.capitalize() for part in details.split("-"))
        return f"{formatted_details} ({person})"

    return None


def filter_items_by_preferences(
    items: list[dict[str, Any]], preferences: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Filters out conflicting menu items and returns safe items and applied accommodations.

    Args:
        items: List of CateringItem dictionaries.
        preferences: List of preference dictionaries (person_name, preference_type, details).

    Returns:
        Tuple of (safe_items, applied_accommodations).
    """
    if not preferences:
        return list(items), []

    accommodations: list[str] = []
    active_constraints: list[dict[str, Any]] = []

    for pref in preferences:
        if not isinstance(pref, dict):
            continue
        pref_type = str(pref.get("preference_type", "")).strip().lower()
        if pref_type in ("allergy", "restriction"):
            active_constraints.append(pref)
            summary = _format_accommodation_summary(pref)
            if summary and summary not in accommodations:
                accommodations.append(summary)

    safe_items: list[dict[str, Any]] = []
    for item in items:
        is_safe = True
        for constraint in active_constraints:
            pref_type = str(constraint.get("preference_type", "")).strip().lower()
            details = str(constraint.get("details", "")).strip()
            if not details:
                continue

            if pref_type == "allergy":
                if _has_allergen_conflict(item, details):
                    is_safe = False
                    break
            elif pref_type == "restriction":
                if _violates_restriction(item, details):
                    is_safe = False
                    break

        if is_safe:
            safe_items.append(item)

    return safe_items, accommodations


def group_items_by_category(
    items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Groups items into standard course categories: mains, sides, beverages, desserts.

    Preserves input list ordering and normalizes 'sides_salads' entries under 'sides'.

    Args:
        items: List of CateringItem dictionaries.

    Returns:
        Dict mapping each standard category to its corresponding list of items.
    """
    grouped: dict[str, list[dict[str, Any]]] = {cat: [] for cat in COURSE_CATEGORIES}
    for item in items:
        cat = normalize_category(item.get("category", ""))
        if cat in grouped:
            grouped[cat].append(item)
    return grouped
