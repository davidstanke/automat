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

"""Deterministic evaluation metrics for catering menus and dietary safety.

Used by `agents-cli eval grade` and unit tests in `test_eval_config.py`.

Metrics provided:
1. `dietary_filtering`: Verifies that no prohibited ingredients or active allergens
   appear within proposed catering items, and that an explicit accommodation note
   is included when constraints are active.
2. `menu_structure_compliance`: Verifies that proposals contain exactly 3 thematic
   menus and each menu contains the 4 required courses (mains, sides, beverages, desserts).
"""

from __future__ import annotations

import re
from typing import Any

# Standard allergen keyword dictionary for checking menu items
ALLERGEN_KEYWORDS: dict[str, list[str]] = {
    "peanut": ["peanut", "peanuts", "peanut butter", "peanut oil"],
    "peanuts": ["peanut", "peanuts", "peanut butter", "peanut oil"],
    "shellfish": [
        "shellfish",
        "shrimp",
        "shrimps",
        "crab",
        "crabs",
        "lobster",
        "lobsters",
        "prawn",
        "prawns",
        "clam",
        "clams",
        "mussel",
        "mussels",
        "oyster",
        "oysters",
        "scallop",
        "scallops",
    ],
    "shrimp": [
        "shellfish",
        "shrimp",
        "shrimps",
        "crab",
        "crabs",
        "lobster",
        "lobsters",
        "prawn",
        "prawns",
        "clam",
        "clams",
        "mussel",
        "mussels",
        "oyster",
        "oysters",
        "scallop",
        "scallops",
    ],
    "shrimps": [
        "shellfish",
        "shrimp",
        "shrimps",
        "crab",
        "crabs",
        "lobster",
        "lobsters",
        "prawn",
        "prawns",
        "clam",
        "clams",
        "mussel",
        "mussels",
        "oyster",
        "oysters",
        "scallop",
        "scallops",
    ],
    "tree nut": [
        "tree nut",
        "walnut",
        "almond",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
    ],
    "tree nuts": [
        "tree nut",
        "walnut",
        "almond",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
    ],
    "nut": [
        "nut",
        "peanut",
        "walnut",
        "almond",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
    ],
    "nuts": [
        "nut",
        "peanut",
        "walnut",
        "almond",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
    ],
    "dairy": ["dairy", "milk", "cheese", "cream", "butter", "yogurt"],
    "milk": ["dairy", "milk", "cheese", "cream", "butter", "yogurt"],
    "lactose": ["dairy", "milk", "cheese", "cream", "butter", "yogurt"],
    "gluten": ["gluten", "wheat", "barley", "rye"],
    "wheat": ["gluten", "wheat", "barley", "rye"],
    "celiac": ["gluten", "wheat", "barley", "rye"],
    "soy": ["soy", "soybean", "tofu", "edamame"],
    "soybean": ["soy", "soybean", "tofu", "edamame"],
    "egg": ["egg", "eggs", "mayonnaise"],
    "eggs": ["egg", "eggs", "mayonnaise"],
    "fish": ["fish", "salmon", "tuna", "cod", "halibut", "trout", "anchovy"],
}

REQUIRED_COURSES: dict[str, re.Pattern[str]] = {
    "mains": re.compile(r"\bmain(s|\s+dishes)?\b", re.IGNORECASE),
    "sides": re.compile(r"\bside(s|\s+dishes)?\b", re.IGNORECASE),
    "beverages": re.compile(r"\b(beverage(s)?|drinks?)\b", re.IGNORECASE),
    "desserts": re.compile(r"\bdessert(s)?\b", re.IGNORECASE),
}


def _extract_response_text(
    instance: dict[str, Any] | None, response: Any = None
) -> str:
    """Extracts plain text response from string, dict, or instance structure."""
    if response is not None:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            if "text" in response and isinstance(response["text"], str):
                return response["text"]
            if "parts" in response and isinstance(response["parts"], list):
                return "\n".join(
                    p.get("text", "")
                    for p in response["parts"]
                    if isinstance(p, dict) and p.get("text")
                )
            if "response" in response:
                return _extract_response_text(None, response["response"])
        if isinstance(response, list):
            return "\n".join(_extract_response_text(None, item) for item in response)

    if instance and isinstance(instance, dict):
        if "response" in instance and instance["response"] is not None:
            return _extract_response_text(None, instance["response"])
        if "agent_data" in instance and isinstance(instance["agent_data"], dict):
            texts = []
            for turn in instance["agent_data"].get("turns", []) or []:
                for event in turn.get("events", []) or []:
                    content = event.get("content") or {}
                    for part in content.get("parts", []) or []:
                        if isinstance(part, dict) and part.get("text"):
                            texts.append(part["text"])
            if texts:
                return "\n".join(texts)
    return ""


def _extract_constraint_strings(items: Any) -> list[str]:
    """Extracts a flat list of lowercase dietary constraint strings."""
    if not items:
        return []
    if isinstance(items, str):
        return [items.strip().lower()] if items.strip() else []
    result = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                cleaned = item.strip().lower()
                if cleaned:
                    result.append(cleaned)
            elif isinstance(item, dict):
                val = (
                    item.get("details")
                    or item.get("name")
                    or item.get("allergen")
                    or item.get("preference")
                )
                if val and str(val).strip():
                    result.append(str(val).strip().lower())
    return result


def _has_accommodation_note(text: str, constraints: list[str]) -> bool:
    """Checks whether an explicit accommodation note is present."""
    # Standard phrasing "Filtered to accommodate: ..."
    if re.search(r"\bfiltered\s+to\s+accommodate\b", text, re.IGNORECASE):
        return True

    # Check under Dietary Accommodations heading for non-empty accommodation content
    match = re.search(
        r"#{1,3}\s*Dietary Accommodations\b\s*\n+([^\n#]+)", text, re.IGNORECASE
    )
    if match:
        content = match.group(1).strip()
        if content and len(content) > 3:
            if re.search(
                r"\b(accommodat|filter|safe|substitut|dietary)\b",
                content,
                re.IGNORECASE,
            ):
                return True
            if any(c.lower() in content.lower() for c in constraints):
                return True

    # General explicit phrasing mentioning accommodations
    if re.search(
        r"\b(?:accommodating|accommodated|filtered\s+for)\s+(?:dietary|allerg|safe|preferences?)\b",
        text,
        re.IGNORECASE,
    ):
        return True

    return False


def _check_allergen_contamination(
    food_text: str, allergies: list[str]
) -> tuple[bool, list[str]]:
    """Checks if any active allergy keyword appears within the food items text."""
    violated = []
    for allergen in allergies:
        norm_allergen = allergen.strip().lower()
        if not norm_allergen:
            continue

        keywords = ALLERGEN_KEYWORDS.get(norm_allergen)
        if not keywords:
            keywords = [norm_allergen]
            if norm_allergen.endswith("s"):
                keywords.append(norm_allergen[:-1])
            else:
                keywords.append(norm_allergen + "s")

        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, food_text, re.IGNORECASE):
                violated.append(f"{allergen} ('{kw}' found)")
                break

    return bool(violated), violated


def dietary_filtering(
    instance: dict[str, Any], response: Any = None
) -> dict[str, Any]:
    """Deterministic evaluator for dietary safety and accommodation notes.

    Checks:
    1. Active allergens do not appear within proposed menu items.
    2. Explicit accommodation statement is present when dietary constraints are active.
    """
    text = _extract_response_text(instance, response)
    if not text or not text.strip():
        return {"score": 0.0, "explanation": "Empty response provided."}

    context = instance.get("context") or instance.get("metadata") or {}
    allergies = _extract_constraint_strings(
        context.get("allergies") or instance.get("allergies")
    )
    preferences = _extract_constraint_strings(
        context.get("preferences") or instance.get("preferences")
    )
    restrictions = _extract_constraint_strings(
        context.get("restrictions") or instance.get("restrictions")
    )

    all_constraints = allergies + preferences + restrictions

    # If no dietary constraints were active, requirement is fully satisfied
    if not all_constraints:
        return {
            "score": 1.0,
            "explanation": "No active dietary constraints; filtering requirement satisfied.",
        }

    # Separate out accommodation notes so the notes themselves do not trigger false positive allergen hits
    food_text = text
    if re.search(r"#{1,3}\s*Dietary Accommodations\b", text, re.IGNORECASE):
        food_text = re.split(
            r"#{1,3}\s*Dietary Accommodations\b", text, flags=re.IGNORECASE
        )[0]
    food_text = re.sub(r"(?i)Filtered to accommodate[^\n]*", "", food_text)

    is_contaminated, violated_allergens = _check_allergen_contamination(
        food_text, allergies
    )
    has_note = _has_accommodation_note(text, all_constraints)

    if not is_contaminated and has_note:
        return {
            "score": 1.0,
            "explanation": (
                "Compliant: no prohibited allergens found in menu items, and "
                "explicit dietary accommodation note is present."
            ),
        }

    # Weighted penalty calculation: safety (0.6) and accommodation phrasing (0.4)
    safety_score = 0.0 if is_contaminated else 1.0
    note_score = 1.0 if has_note else 0.0
    score = round(0.6 * safety_score + 0.4 * note_score, 4)
    score = max(0.0, min(1.0, score))

    reasons = []
    if is_contaminated:
        reasons.append(
            f"prohibited allergen(s) found in menu items: {', '.join(violated_allergens)}"
        )
    if not has_note:
        reasons.append("missing explicit dietary accommodation note")

    explanation = f"Dietary filtering penalized ({'; '.join(reasons)})."
    return {"score": float(score), "explanation": explanation}


def _extract_candidate_menus(text: str) -> list[str]:
    """Extracts candidate menu blocks from response text."""
    if not text or not text.strip():
        return []

    # Isolate Proposed Catering Menus section if present
    match = re.search(
        r"###\s*Proposed Catering Menus\b(.*?)(?=\n#{1,3}\s+(?!Menu\b)[A-Za-z]|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    catering_text = match.group(1) if match else text

    # Strip off dietary accommodations section if within catering text
    catering_text = re.split(
        r"(?:^|\n)#{1,3}\s*Dietary Accommodations\b",
        catering_text,
        flags=re.IGNORECASE,
    )[0]

    # Split on headers/items that introduce individual menus:
    # 1. Level 3 or 4 headers: #### Menu 1, ### Menu 1, #### Baja Fiesta
    # 2. Numbered bold items: 1. **Baja Fiesta**
    # 3. Plain text Menu markers: Menu 1:
    raw_blocks = re.split(
        r"(?:^|\n)(?=#{3,4}\s+|\bMenu\s*\d+\s*[:\-]|^\s*\d+[\.\)]\s+\*\*)",
        catering_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    course_indicator = re.compile(
        r"\b(main(s|\s+dishes)?|side(s|\s+dishes)?|beverage(s)?|drinks?|dessert(s)?)\b",
        re.IGNORECASE,
    )

    candidate_menus = [
        b.strip()
        for b in raw_blocks
        if b.strip() and course_indicator.search(b)
    ]
    return candidate_menus


def menu_structure_compliance(
    instance: dict[str, Any], response: Any = None
) -> dict[str, Any]:
    """Deterministic evaluator for 3 thematic menus and 4 courses per menu.

    Checks:
    1. Exactly 3 menus are proposed.
    2. Each menu contains mains, sides, beverages, and desserts.
    """
    text = _extract_response_text(instance, response)
    if not text or not text.strip():
        return {"score": 0.0, "explanation": "Empty response provided."}

    candidate_menus = _extract_candidate_menus(text)
    num_menus = len(candidate_menus)

    if num_menus == 0:
        return {"score": 0.0, "explanation": "No catering menus detected in response."}

    total_courses_present = 0
    for menu in candidate_menus:
        present = [
            c_name
            for c_name, c_regex in REQUIRED_COURSES.items()
            if c_regex.search(menu)
        ]
        total_courses_present += len(present)

    expected_menus = 3
    expected_courses_per_menu = 4
    total_expected_courses = expected_menus * expected_courses_per_menu  # 12

    # Ratio of present courses across the candidate menus
    courses_ratio = total_courses_present / (num_menus * expected_courses_per_menu)

    # Menu count factor (penalizes count != 3)
    if num_menus == 3:
        menu_factor = 1.0
    else:
        menu_factor = max(0.0, 1.0 - abs(num_menus - 3) * 0.25)

    if num_menus == 3 and total_courses_present == total_expected_courses:
        score = 1.0
        explanation = "Compliant: exactly 3 menus found, each containing all 4 courses."
    else:
        # Bounded between 0.0 and strictly < 1.0 (capped at 0.95 when non-compliant)
        score = min(0.95, round(menu_factor * courses_ratio, 4))
        score = max(0.0, score)
        explanation = (
            f"Non-compliant: found {num_menus} menu(s) (expected 3) with "
            f"{total_courses_present} total course instances (expected 12)."
        )

    return {"score": float(score), "explanation": explanation}


def evaluate(instance: dict[str, Any]) -> dict[str, Any]:
    """General dispatcher for ADK eval framework."""
    metric = instance.get("metric_name")
    if metric == "menu_structure_compliance":
        return menu_structure_compliance(instance)
    if metric == "dietary_filtering":
        return dietary_filtering(instance)

    context = instance.get("context") or instance.get("metadata") or {}
    if "allergies" in context or "preferences" in context:
        return dietary_filtering(instance)
    return menu_structure_compliance(instance)
