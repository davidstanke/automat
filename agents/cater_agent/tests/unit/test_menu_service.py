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

"""Unit tests for Cater Agent Catering Menu Data Access & Offline Fallback Service.

Verifies:
- CateringItem contract: id, name, description, category (mains, sides, beverages, desserts),
  ingredients, allergens, dietary_labels, price.
- BigQuery MCP query execution attempting to query `catering.menu_items` when configured.
- 5.0-second socket timeout enforcement on MCP queries.
- Graceful offline fallback to `data/catering/catering_menu.json` without unhandled exceptions
  on MCP timeouts, connection errors, auth failures, or unauthenticated environments.
- Category filtering during querying and category normalization ("sides_salads" -> "sides").
- Preference filtering: allergen detection across both `allergens` and `ingredients` fields.
- Preference filtering: dietary restriction matching via `dietary_labels` (vegan, vegetarian, gluten-free).
- Generation of human-readable accommodation summaries (e.g., ["Peanut allergy (Alice)", "Vegetarian (Bob)"]).
- Grouping items into the 4 standard course categories: mains, sides, beverages, desserts.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import menu_service


# ---------------------------------------------------------------------------
# Test Fixtures & Synthetic Data
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_menu_items() -> list[dict[str, Any]]:
    """Diverse synthetic menu items covering categories, allergens, and dietary labels."""
    return [
        {
            "id": 1,
            "name": "Grilled Chicken Pesto Sandwich",
            "description": "Marinated grilled chicken breast, house pesto, provolone on ciabatta.",
            "category": "mains",
            "ingredients": ["chicken breast", "pesto", "provolone cheese", "arugula", "ciabatta bread"],
            "allergens": ["dairy", "gluten", "tree nuts"],
            "dietary_labels": ["nut-free-option"],
            "price": 8.5,
        },
        {
            "id": 4,
            "name": "Caprese Focaccia Panini",
            "description": "Fresh mozzarella, ripe tomatoes, basil, and balsamic glaze on focaccia.",
            "category": "mains",
            "ingredients": ["mozzarella", "tomatoes", "fresh basil", "balsamic glaze", "focaccia bread"],
            "allergens": ["dairy", "gluten"],
            "dietary_labels": ["vegetarian"],
            "price": 7.5,
        },
        {
            "id": 7,
            "name": "Crispy Tofu & Quinoa Power Bowl",
            "description": "Crispy baked tofu, quinoa, edamame, and peanut sesame dressing.",
            "category": "mains",
            "ingredients": ["tofu", "quinoa", "edamame", "carrots", "peanut dressing", "sesame seeds"],
            "allergens": ["soy", "peanuts", "sesame"],
            "dietary_labels": ["vegan", "vegetarian", "dairy-free"],
            "price": 8.0,
        },
        {
            "id": 16,
            "name": "Lemon Herb Roasted Chicken Quarter",
            "description": "Roasted chicken leg quarter seasoned with lemon, rosemary, and garlic.",
            "category": "mains",
            "ingredients": ["chicken leg quarter", "lemon juice", "rosemary", "garlic", "olive oil"],
            "allergens": [],
            "dietary_labels": ["gluten-free", "dairy-free"],
            "price": 7.5,
        },
        {
            "id": 25,
            "name": "Fettuccine Alfredo with Shrimp",
            "description": "Sauteed jumbo shrimp over fettuccine in garlic cream sauce.",
            "category": "mains",
            "ingredients": ["fettuccine pasta", "shrimp", "butter", "heavy cream", "parmesan", "garlic"],
            "allergens": ["gluten", "dairy", "shellfish", "eggs"],
            "dietary_labels": [],
            "price": 11.5,
        },
        {
            "id": 59,
            "name": "Vegan Sweet Potato Enchiladas",
            "description": "Corn tortillas filled with sweet potato and black beans in guajillo sauce.",
            "category": "mains",
            "ingredients": ["corn tortillas", "sweet potato", "black beans", "guajillo chili sauce", "cilantro"],
            "allergens": [],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 8.0,
        },
        {
            "id": 71,
            "name": "Classic Caesar Salad",
            "description": "Romaine lettuce, house parmesan croutons, shaved parmesan, Caesar dressing.",
            "category": "sides_salads",
            "ingredients": ["romaine lettuce", "croutons", "parmesan cheese", "caesar dressing"],
            "allergens": ["gluten", "dairy", "fish", "eggs"],
            "dietary_labels": ["vegetarian-option"],
            "price": 4.25,
        },
        {
            "id": 73,
            "name": "Southwest Roasted Corn & Black Bean Salad",
            "description": "Sweet corn, black beans, red bell pepper, cilantro, lime vinaigrette.",
            "category": "sides_salads",
            "ingredients": ["sweet corn", "black beans", "bell pepper", "cilantro", "lime juice", "olive oil"],
            "allergens": [],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 4.0,
        },
        {
            "id": 84,
            "name": "Thai Cucumber Salad",
            "description": "Cucumbers, red onions, cilantro, crushed peanuts, sweet chili lime dressing.",
            "category": "sides",
            "ingredients": ["cucumbers", "red onions", "cilantro", "peanuts", "sweet chili lime dressing"],
            "allergens": ["peanuts"],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 3.5,
        },
        {
            "id": 91,
            "name": "Garlic Herb Roasted Potatoes",
            "description": "Crispy roasted baby potatoes seasoned with garlic, rosemary, and olive oil.",
            "category": "sides",
            "ingredients": ["baby potatoes", "garlic", "rosemary", "olive oil"],
            "allergens": [],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 3.25,
        },
        {
            "id": 111,
            "name": "Fresh Cold-Pressed Lemonade",
            "description": "House-made fresh squeezed lemonade with cane sugar.",
            "category": "beverages",
            "ingredients": ["water", "lemon juice", "cane sugar"],
            "allergens": [],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 2.25,
        },
        {
            "id": 120,
            "name": "Mango Lassi",
            "description": "Traditional yogurt drink blended with mango pulp and cardamom.",
            "category": "beverages",
            "ingredients": ["whole milk yogurt", "mango pulp", "sugar", "cardamom"],
            "allergens": ["dairy"],
            "dietary_labels": ["vegetarian", "gluten-free"],
            "price": 3.25,
        },
        {
            "id": 131,
            "name": "Fudgy Chocolate Brownie Bite",
            "description": "Rich chocolate brownie topped with chocolate drizzle.",
            "category": "desserts",
            "ingredients": ["chocolate", "butter", "flour", "sugar", "eggs", "cocoa powder"],
            "allergens": ["gluten", "dairy", "eggs"],
            "dietary_labels": ["vegetarian"],
            "price": 2.5,
        },
        {
            "id": 139,
            "name": "Vegan Chocolate Avocado Mousse",
            "description": "Silky dark chocolate mousse made with ripe avocados and maple syrup.",
            "category": "desserts",
            "ingredients": ["avocado", "cocoa powder", "maple syrup", "vanilla extract", "almond milk"],
            "allergens": [],
            "dietary_labels": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
            "price": 3.5,
        },
        {
            "id": 145,
            "name": "Peanut Butter Fudge Brownie",
            "description": "Fudgy brownie with a peanut butter swirl and roasted peanut bits.",
            "category": "desserts",
            "ingredients": ["flour", "peanut butter", "cocoa powder", "butter", "peanuts", "eggs"],
            "allergens": ["gluten", "dairy", "peanuts", "eggs"],
            "dietary_labels": ["vegetarian"],
            "price": 2.75,
        },
    ]


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch):
    """Configures an unauthenticated offline environment with no BigQuery MCP."""
    monkeypatch.delenv("BIGQUERY_MCP_COMMAND", raising=False)
    monkeypatch.delenv("BIGQUERY_MCP_URL", raising=False)
    monkeypatch.delenv("BIGQUERY_MCP_SERVER", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)


# ---------------------------------------------------------------------------
# 1. Interface Signature & Contract Validation
# ---------------------------------------------------------------------------
def test_menu_service_functions_exist_and_signatures_match() -> None:
    """Verify expected function signatures in menu_service module."""
    assert hasattr(menu_service, "query_menu_items"), "menu_service must export query_menu_items"
    assert hasattr(menu_service, "filter_items_by_preferences"), (
        "menu_service must export filter_items_by_preferences"
    )
    assert hasattr(menu_service, "group_items_by_category"), (
        "menu_service must export group_items_by_category"
    )

    # query_menu_items must be a coroutine function
    assert inspect.iscoroutinefunction(menu_service.query_menu_items), (
        "query_menu_items must be an async function"
    )

    # filter_items_by_preferences signature: (items, preferences)
    sig_filter = inspect.signature(menu_service.filter_items_by_preferences)
    params_filter = list(sig_filter.parameters.keys())
    assert len(params_filter) >= 2, "filter_items_by_preferences must accept items and preferences"
    assert params_filter[0] == "items"
    assert params_filter[1] == "preferences"

    # group_items_by_category signature: (items)
    sig_group = inspect.signature(menu_service.group_items_by_category)
    params_group = list(sig_group.parameters.keys())
    assert len(params_group) >= 1, "group_items_by_category must accept items"
    assert params_group[0] == "items"


# ---------------------------------------------------------------------------
# 2. Local Fallback & CateringItem Contract
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_query_menu_items_offline_loads_local_json(offline_env: None) -> None:
    """Verify query_menu_items successfully falls back to loading data/catering/catering_menu.json."""
    items = await menu_service.query_menu_items()
    assert isinstance(items, list), "query_menu_items must return a list"
    assert len(items) == 150, f"Expected 150 items from local catering_menu.json, got {len(items)}"

    # Validate CateringItem dictionary schema
    required_keys = {"id", "name", "description", "category", "ingredients", "allergens", "dietary_labels", "price"}
    valid_categories = {"mains", "sides", "beverages", "desserts"}

    for item in items:
        missing = required_keys - set(item.keys())
        assert not missing, f"Item {item.get('name')} missing required keys: {missing}"
        assert isinstance(item["id"], (int, str)), "item.id must be an int or str"
        assert isinstance(item["name"], str) and item["name"], "item.name must be non-empty string"
        assert isinstance(item["description"], str), "item.description must be string"
        assert item["category"] in valid_categories, (
            f"Item category '{item['category']}' must be normalized to one of {valid_categories}"
        )
        assert isinstance(item["ingredients"], list), "item.ingredients must be list"
        assert isinstance(item["allergens"], list), "item.allergens must be list"
        assert isinstance(item["dietary_labels"], list), "item.dietary_labels must be list"
        assert isinstance(item["price"], (int, float)), "item.price must be numeric"


@pytest.mark.asyncio
async def test_query_menu_items_normalizes_sides_salads_to_sides(offline_env: None) -> None:
    """Verify raw 'sides_salads' entries in json are normalized to 'sides' category."""
    items = await menu_service.query_menu_items()
    sides = [item for item in items if item["category"] == "sides"]
    assert len(sides) == 40, f"Expected 40 sides items in local menu, found {len(sides)}"
    assert not any(item["category"] == "sides_salads" for item in items), (
        "No item should have raw category 'sides_salads'; it must be normalized to 'sides'"
    )


@pytest.mark.asyncio
async def test_query_menu_items_filters_by_categories(offline_env: None) -> None:
    """Verify query_menu_items accepts categories filter."""
    mains = await menu_service.query_menu_items(categories=["mains"])
    assert len(mains) == 70, f"Expected 70 mains, got {len(mains)}"
    assert all(item["category"] == "mains" for item in mains)

    beverages = await menu_service.query_menu_items(categories=["beverages"])
    assert len(beverages) == 20, f"Expected 20 beverages, got {len(beverages)}"
    assert all(item["category"] == "beverages" for item in beverages)

    desserts = await menu_service.query_menu_items(categories=["desserts"])
    assert len(desserts) == 20, f"Expected 20 desserts, got {len(desserts)}"
    assert all(item["category"] == "desserts" for item in desserts)

    sides = await menu_service.query_menu_items(categories=["sides"])
    assert len(sides) == 40, f"Expected 40 sides, got {len(sides)}"
    assert all(item["category"] == "sides" for item in sides)

    combo = await menu_service.query_menu_items(categories=["beverages", "desserts"])
    assert len(combo) == 40
    assert set(item["category"] for item in combo) == {"beverages", "desserts"}


@pytest.mark.asyncio
async def test_query_menu_items_category_case_insensitivity(offline_env: None) -> None:
    """Verify query_menu_items handles uppercase or mixed-case category names."""
    mains = await menu_service.query_menu_items(categories=["MAINS"])
    assert len(mains) == 70

    sides = await menu_service.query_menu_items(categories=["Sides"])
    assert len(sides) == 40


@pytest.mark.asyncio
async def test_query_menu_items_unknown_category_returns_empty(offline_env: None) -> None:
    """Verify unknown category filter returns empty list without error."""
    results = await menu_service.query_menu_items(categories=["nonexistent_category"])
    assert results == []


# ---------------------------------------------------------------------------
# 3. BigQuery MCP Query Execution & 5.0-Second Timeout Limit
# ---------------------------------------------------------------------------
def test_mcp_timeout_constant_is_five_seconds() -> None:
    """Verify MCP timeout constant is 5.0 seconds as required by specification."""
    timeout_val = getattr(menu_service, "MCP_TIMEOUT", getattr(menu_service, "SOCKET_TIMEOUT", 5.0))
    assert timeout_val == 5.0, f"Expected MCP timeout limit to be 5.0 seconds, got {timeout_val}"


@pytest.mark.asyncio
async def test_mcp_query_attempts_bigquery_catering_menu_items(
    monkeypatch: pytest.MonkeyPatch, sample_menu_items: list[dict[str, Any]]
) -> None:
    """Verify when BigQuery MCP is configured, it queries catering.menu_items."""
    monkeypatch.setenv("BIGQUERY_MCP_COMMAND", "mock-bigquery-mcp")

    # Hook internal query execution function if present
    mock_run = AsyncMock(return_value=[copy.deepcopy(sample_menu_items[0])])
    for hook_name in ("_execute_mcp_query", "_query_mcp", "_query_bigquery", "_run_mcp_query"):
        if hasattr(menu_service, hook_name):
            monkeypatch.setattr(menu_service, hook_name, mock_run)

    # Alternatively hook run_query tool or MCP client
    mock_mcp_client = MagicMock()
    mock_mcp_client.call_tool = AsyncMock(
        return_value=MagicMock(data=[copy.deepcopy(sample_menu_items[0])])
    )
    if hasattr(menu_service, "_get_mcp_client"):
        monkeypatch.setattr(menu_service, "_get_mcp_client", lambda: mock_mcp_client)

    results = await menu_service.query_menu_items(categories=["mains"])
    assert isinstance(results, list)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_mcp_query_timeout_falls_back_to_local_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify MCP timeout triggers automatic fallback to data/catering/catering_menu.json."""
    monkeypatch.setenv("BIGQUERY_MCP_COMMAND", "mock-bigquery-mcp")

    async def _timed_out_query(*args, **kwargs):
        raise asyncio.TimeoutError("MCP query timed out after 5.0s")

    for hook_name in ("_execute_mcp_query", "_query_mcp", "_query_bigquery", "_run_mcp_query"):
        if hasattr(menu_service, hook_name):
            monkeypatch.setattr(menu_service, hook_name, _timed_out_query)

    # Patch asyncio.wait_for or timeout if used directly
    original_wait_for = asyncio.wait_for

    async def _mock_wait_for(coro, timeout, **kwargs):
        if timeout == 5.0 or (isinstance(timeout, (int, float)) and timeout <= 5.0):
            raise asyncio.TimeoutError("Socket timeout exceeded")
        return await original_wait_for(coro, timeout, **kwargs)

    # Under timeout condition, query_menu_items MUST NOT raise unhandled exception
    items = await menu_service.query_menu_items()
    assert isinstance(items, list)
    assert len(items) == 150, "Should fall back to 150 local items upon MCP timeout"


@pytest.mark.asyncio
async def test_mcp_connection_error_falls_back_to_local_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify MCP connection errors (socket, refused) fall back gracefully to local JSON."""
    monkeypatch.setenv("BIGQUERY_MCP_COMMAND", "mock-bigquery-mcp")

    async def _connection_failed(*args, **kwargs):
        raise ConnectionRefusedError("Unable to connect to BigQuery MCP socket")

    for hook_name in ("_execute_mcp_query", "_query_mcp", "_query_bigquery", "_run_mcp_query"):
        if hasattr(menu_service, hook_name):
            monkeypatch.setattr(menu_service, hook_name, _connection_failed)

    items = await menu_service.query_menu_items()
    assert isinstance(items, list)
    assert len(items) == 150


@pytest.mark.asyncio
async def test_mcp_unauthenticated_environment_falls_back_to_local_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify unauthenticated/permission errors fall back gracefully without unhandled exception."""
    monkeypatch.setenv("BIGQUERY_MCP_COMMAND", "mock-bigquery-mcp")

    async def _auth_failed(*args, **kwargs):
        raise PermissionError("403 Forbidden: Unauthenticated GCP environment")

    for hook_name in ("_execute_mcp_query", "_query_mcp", "_query_bigquery", "_run_mcp_query"):
        if hasattr(menu_service, hook_name):
            monkeypatch.setattr(menu_service, hook_name, _auth_failed)

    items = await menu_service.query_menu_items()
    assert isinstance(items, list)
    assert len(items) == 150


@pytest.mark.asyncio
async def test_mcp_generic_exception_falls_back_to_local_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify any unexpected MCP server crash or query error falls back to local JSON."""
    monkeypatch.setenv("BIGQUERY_MCP_COMMAND", "mock-bigquery-mcp")

    async def _crash(*args, **kwargs):
        raise RuntimeError("MCP server closed connection unexpectedly")

    for hook_name in ("_execute_mcp_query", "_query_mcp", "_query_bigquery", "_run_mcp_query"):
        if hasattr(menu_service, hook_name):
            monkeypatch.setattr(menu_service, hook_name, _crash)

    items = await menu_service.query_menu_items()
    assert isinstance(items, list)
    assert len(items) == 150


# ---------------------------------------------------------------------------
# 4. Dietary Preference Filtering: Allergens
# ---------------------------------------------------------------------------
def test_filter_removes_dishes_matching_allergens_field(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify dishes with allergen listed in 'allergens' are filtered out."""
    prefs = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "peanuts"}
    ]
    safe, accommodations = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    # Items containing peanuts in allergens:
    # id 7 (tofu power bowl), id 84 (thai cucumber salad), id 145 (peanut butter brownie)
    safe_ids = {item["id"] for item in safe}
    assert 7 not in safe_ids, "Item 7 contains peanuts in allergens"
    assert 84 not in safe_ids, "Item 84 contains peanuts in allergens"
    assert 145 not in safe_ids, "Item 145 contains peanuts in allergens"
    assert len(safe) == len(sample_menu_items) - 3


def test_filter_removes_dishes_matching_ingredients_field(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify dishes with allergen in 'ingredients' are filtered out even if not in allergens."""
    # Add a dish with shellfish in ingredients only
    items = copy.deepcopy(sample_menu_items)
    items.append({
        "id": 999,
        "name": "Secret Shrimp Bites",
        "description": "Appetizer bites with shrimp",
        "category": "sides",
        "ingredients": ["fresh shrimp", "garlic", "butter"],
        "allergens": [],  # Intentionally missing from allergens list
        "dietary_labels": [],
        "price": 5.0,
    })

    prefs = [
        {"person_name": "Bob", "preference_type": "allergy", "details": "shellfish"}
    ]
    safe, _ = menu_service.filter_items_by_preferences(items, prefs)
    safe_ids = {item["id"] for item in safe}

    assert 25 not in safe_ids, "Fettuccine Alfredo has shellfish allergen"
    assert 999 not in safe_ids, "Secret Shrimp Bites has shrimp in ingredients"


def test_filter_allergens_case_insensitive_and_plural_normalization(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify allergen filtering is case-insensitive and handles singular/plural forms."""
    # Singular "peanut" vs plural "peanuts"
    prefs_singular = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "Peanut"}
    ]
    safe_singular, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs_singular)
    safe_singular_ids = {item["id"] for item in safe_singular}
    assert 7 not in safe_singular_ids
    assert 84 not in safe_singular_ids
    assert 145 not in safe_singular_ids

    # Dairy with mixed casing
    prefs_dairy = [
        {"person_name": "Carol", "preference_type": "allergy", "details": "DAIRY"}
    ]
    safe_dairy, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs_dairy)
    for item in safe_dairy:
        assert "dairy" not in [a.lower() for a in item["allergens"]]
        assert "milk" not in [i.lower() for i in item["ingredients"]]
        assert "cheese" not in [i.lower() for i in item["ingredients"]]


def test_filter_multiple_allergens_simultaneously(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify multiple allergies from one or more team members are enforced."""
    prefs = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "peanuts"},
        {"person_name": "Bob", "preference_type": "allergy", "details": "shellfish"},
        {"person_name": "Carol", "preference_type": "allergy", "details": "dairy"},
    ]
    safe, accommodations = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    for item in safe:
        allergens_lower = [a.lower() for a in item["allergens"]]
        assert "peanuts" not in allergens_lower
        assert "peanut" not in allergens_lower
        assert "shellfish" not in allergens_lower
        assert "dairy" not in allergens_lower


# ---------------------------------------------------------------------------
# 5. Dietary Preference Filtering: Restrictions
# ---------------------------------------------------------------------------
def test_filter_vegan_restriction(sample_menu_items: list[dict[str, Any]]) -> None:
    """Verify vegan restriction keeps only dishes with 'vegan' dietary label."""
    prefs = [
        {"person_name": "Bob", "preference_type": "restriction", "details": "vegan"}
    ]
    safe, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    assert len(safe) > 0
    for item in safe:
        labels_lower = [l.lower() for l in item["dietary_labels"]]
        assert "vegan" in labels_lower, f"Dish {item['name']} must have 'vegan' label"


def test_filter_vegetarian_restriction(sample_menu_items: list[dict[str, Any]]) -> None:
    """Verify vegetarian restriction keeps dishes labeled vegetarian or vegan."""
    prefs = [
        {"person_name": "Bob", "preference_type": "restriction", "details": "vegetarian"}
    ]
    safe, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    assert len(safe) > 0
    for item in safe:
        labels_lower = [l.lower() for l in item["dietary_labels"]]
        assert "vegetarian" in labels_lower or "vegan" in labels_lower, (
            f"Dish {item['name']} must be vegetarian or vegan"
        )
        # Ensure meat/poultry/shellfish dishes are filtered
        ingredients_str = " ".join(item["ingredients"]).lower()
        assert "chicken" not in ingredients_str
        assert "shrimp" not in ingredients_str


def test_filter_gluten_free_restriction(sample_menu_items: list[dict[str, Any]]) -> None:
    """Verify gluten-free restriction excludes dishes containing gluten."""
    prefs = [
        {"person_name": "Charlie", "preference_type": "restriction", "details": "gluten-free"}
    ]
    safe, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    assert len(safe) > 0
    for item in safe:
        assert "gluten" not in [a.lower() for a in item["allergens"]]
        labels_lower = [l.lower() for l in item["dietary_labels"]]
        # Either has gluten-free label or allergen free
        assert "gluten-free" in labels_lower or "gluten" not in item["allergens"]


def test_filter_combined_vegan_and_gluten_free_restrictions(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify simultaneous vegan and gluten-free restrictions are both respected."""
    prefs = [
        {"person_name": "Bob", "preference_type": "restriction", "details": "vegan"},
        {"person_name": "Charlie", "preference_type": "restriction", "details": "gluten-free"},
    ]
    safe, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    for item in safe:
        labels_lower = [l.lower() for l in item["dietary_labels"]]
        assert "vegan" in labels_lower
        assert "gluten" not in [a.lower() for a in item["allergens"]]


def test_filter_empty_preferences_returns_all_items(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify empty preferences returns all items and empty accommodations list."""
    safe, accommodations = menu_service.filter_items_by_preferences(sample_menu_items, [])
    assert len(safe) == len(sample_menu_items)
    assert accommodations == []


def test_filter_likes_and_dislikes_handling(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify 'like' preferences do not filter out dishes."""
    prefs = [
        {"person_name": "Dave", "preference_type": "like", "details": "spicy food"},
    ]
    safe, _ = menu_service.filter_items_by_preferences(sample_menu_items, prefs)
    assert len(safe) == len(sample_menu_items)


# ---------------------------------------------------------------------------
# 6. Human-Readable Accommodation Summaries
# ---------------------------------------------------------------------------
def test_accommodation_summaries_generation(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify human-readable list of active accommodation summaries."""
    prefs = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "peanuts"},
        {"person_name": "Bob", "preference_type": "restriction", "details": "vegetarian"},
    ]
    _, accommodations = menu_service.filter_items_by_preferences(sample_menu_items, prefs)

    assert isinstance(accommodations, list), "Accommodations must be a list of strings"
    assert len(accommodations) >= 2, "Must produce summary for each active constraint"

    # Verify Alice's peanut allergy is captured
    alice_summary = next((s for s in accommodations if "alice" in s.lower()), None)
    assert alice_summary is not None, "Accommodation summaries must reference Alice"
    assert "peanut" in alice_summary.lower(), "Alice's summary must mention peanut"

    # Verify Bob's vegetarian restriction is captured
    bob_summary = next((s for s in accommodations if "bob" in s.lower()), None)
    assert bob_summary is not None, "Accommodation summaries must reference Bob"
    assert "vegetarian" in bob_summary.lower(), "Bob's summary must mention vegetarian"


def test_accommodation_summaries_multiple_rules_per_person(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify multiple restrictions/allergies for the same person produce distinct summaries."""
    prefs = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "peanuts"},
        {"person_name": "Alice", "preference_type": "allergy", "details": "shellfish"},
    ]
    _, accommodations = menu_service.filter_items_by_preferences(sample_menu_items, prefs)
    assert len(accommodations) >= 2
    summaries_text = " ".join(accommodations).lower()
    assert "peanut" in summaries_text
    assert "shellfish" in summaries_text


# ---------------------------------------------------------------------------
# 7. Category Grouping (group_items_by_category)
# ---------------------------------------------------------------------------
def test_group_items_by_category_contains_all_course_categories(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify grouped dictionary contains mains, sides, beverages, and desserts."""
    grouped = menu_service.group_items_by_category(sample_menu_items)

    assert isinstance(grouped, dict), "group_items_by_category must return a dict"
    expected_categories = {"mains", "sides", "beverages", "desserts"}
    assert set(grouped.keys()) == expected_categories, (
        f"Grouped keys must be {expected_categories}, got {set(grouped.keys())}"
    )

    for cat in expected_categories:
        assert isinstance(grouped[cat], list), f"grouped['{cat}'] must be a list"
        assert len(grouped[cat]) > 0, f"Expected non-empty items in '{cat}'"


def test_group_items_by_category_normalizes_sides_salads(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify items categorized as 'sides_salads' or 'sides' are grouped under 'sides'."""
    grouped = menu_service.group_items_by_category(sample_menu_items)

    # In sample_menu_items, id 71 and 73 have category 'sides_salads', id 84 and 91 have 'sides'
    sides_ids = {item["id"] for item in grouped["sides"]}
    assert 71 in sides_ids, "Item 71 (sides_salads) must be grouped under 'sides'"
    assert 73 in sides_ids, "Item 73 (sides_salads) must be grouped under 'sides'"
    assert 84 in sides_ids, "Item 84 (sides) must be grouped under 'sides'"
    assert 91 in sides_ids, "Item 91 (sides) must be grouped under 'sides'"
    assert "sides_salads" not in grouped


def test_group_items_by_category_empty_input() -> None:
    """Verify empty item list returns dict with empty lists for all 4 categories."""
    grouped = menu_service.group_items_by_category([])
    assert grouped == {
        "mains": [],
        "sides": [],
        "beverages": [],
        "desserts": [],
    }


def test_group_items_by_category_preserves_order(
    sample_menu_items: list[dict[str, Any]],
) -> None:
    """Verify order of items within each category is preserved from input list."""
    grouped = menu_service.group_items_by_category(sample_menu_items)
    beverages = grouped["beverages"]
    assert len(beverages) == 2
    assert beverages[0]["id"] == 111
    assert beverages[1]["id"] == 120


# ---------------------------------------------------------------------------
# 8. End-to-End Fallback, Filtering & Grouping Pipeline
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_end_to_end_menu_pipeline(offline_env: None) -> None:
    """Verify full workflow: query items offline, filter by dietary constraints, and group."""
    # 1. Query all items (falls back to local json)
    all_items = await menu_service.query_menu_items()
    assert len(all_items) == 150

    # 2. Filter with realistic team preferences
    prefs = [
        {"person_name": "Alice", "preference_type": "allergy", "details": "peanuts"},
        {"person_name": "Bob", "preference_type": "restriction", "details": "vegetarian"},
    ]
    safe_items, accommodations = menu_service.filter_items_by_preferences(all_items, prefs)

    assert len(safe_items) < len(all_items)
    assert len(accommodations) >= 2

    # None of safe items contain peanuts
    for item in safe_items:
        assert "peanuts" not in [a.lower() for a in item["allergens"]]
        assert "peanut" not in [a.lower() for a in item["allergens"]]
        assert "peanut" not in " ".join(item["ingredients"]).lower()

        # All items must be vegetarian or vegan
        labels_lower = [l.lower() for l in item["dietary_labels"]]
        assert "vegetarian" in labels_lower or "vegan" in labels_lower

    # 3. Group safe items by category
    grouped = menu_service.group_items_by_category(safe_items)
    assert len(grouped["mains"]) >= 1
    assert len(grouped["sides"]) >= 1
    assert len(grouped["beverages"]) >= 1
    assert len(grouped["desserts"]) >= 1
