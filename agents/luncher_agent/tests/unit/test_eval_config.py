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

"""Unit tests for catering evaluation dataset, eval_config.yaml, and catering_eval metrics.

Validates:
1. catering-dataset.json schema, structure, and coverage of all 5 BDD specification scenarios.
2. eval_config.yaml registration of catering custom metrics.
3. Custom evaluators (dietary_filtering, menu_structure_compliance) in catering_eval.py
   scoring passing and failing mock responses deterministically.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import types
from typing import Any

import pytest
import yaml

# Base paths
AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = AGENT_ROOT / "tests" / "eval"
DATASETS_DIR = EVAL_DIR / "datasets"
CATERING_DATASET_FILE = DATASETS_DIR / "catering-dataset.json"
EVAL_CONFIG_FILE = EVAL_DIR / "eval_config.yaml"
CATERING_EVAL_FILE = EVAL_DIR / "catering_eval.py"


def _load_catering_eval_module() -> types.ModuleType:
    """Dynamically load catering_eval module from tests/eval/catering_eval.py."""
    assert CATERING_EVAL_FILE.exists(), f"Target file does not exist: {CATERING_EVAL_FILE}"
    spec = importlib.util.spec_from_file_location("catering_eval", CATERING_EVAL_FILE)
    assert spec is not None and spec.loader is not None, f"Could not create spec for {CATERING_EVAL_FILE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_catering_dataset_instances() -> list[dict[str, Any]]:
    """Loads and standardizes instances from catering-dataset.json."""
    assert CATERING_DATASET_FILE.exists(), f"Dataset file does not exist: {CATERING_DATASET_FILE}"
    with open(CATERING_DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "eval_cases" in data and isinstance(data["eval_cases"], list):
            return data["eval_cases"]
        if "instances" in data and isinstance(data["instances"], list):
            return data["instances"]
    pytest.fail(f"catering-dataset.json must be a list or dict with eval_cases/instances, got {type(data)}")


# ==============================================================================
# 1. Dataset Verification (catering-dataset.json)
# ==============================================================================


def test_catering_dataset_exists_and_is_valid_json() -> None:
    """Verifies catering-dataset.json exists and contains valid JSON."""
    assert CATERING_DATASET_FILE.exists(), f"catering-dataset.json not found at {CATERING_DATASET_FILE}"
    with open(CATERING_DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data is not None, "catering-dataset.json is empty"


def test_catering_dataset_instances_schema() -> None:
    """Validates ADK eval instance schema: input/prompt, expected patterns/reference, context."""
    instances = _load_catering_dataset_instances()
    assert len(instances) >= 5, f"Expected at least 5 eval cases for BDD scenarios, found {len(instances)}"

    for idx, inst in enumerate(instances):
        assert isinstance(inst, dict), f"Instance #{idx} is not a dict"

        # Input contract: input or prompt (role + parts or text) or agent_data
        has_input = (
            "input" in inst
            or "prompt" in inst
            or ("agent_data" in inst and "turns" in inst["agent_data"])
        )
        assert has_input, f"Instance #{idx} must have 'input', 'prompt', or 'agent_data.turns'"

        # Expected output contract: expected_output_patterns or reference
        has_expected = "expected_output_patterns" in inst or "reference" in inst
        assert has_expected, f"Instance #{idx} must have 'expected_output_patterns' or 'reference'"

        # Context contract: context or metadata
        has_context = "context" in inst or "metadata" in inst or "eval_case_id" in inst
        assert has_context, f"Instance #{idx} must have 'context', 'metadata', or 'eval_case_id'"


def test_catering_dataset_covers_all_five_bdd_scenarios() -> None:
    """Verifies catering-dataset.json covers the 5 specification BDD scenarios:
    1. Standard lunch request expecting 3 thematic menus with 4 courses each.
    2. Active allergies (peanuts, shellfish, vegetarian) expecting allergen exclusion and explicit filtering notes.
    3. Pure dietary update expecting confirmation and no meeting proposal.
    4. Booking with catering selection expecting booking ID and catering summary.
    5. Offline / local fallback when MCP is unavailable.
    """
    instances = _load_catering_dataset_instances()
    raw_text = json.dumps(instances).lower()

    # Scenario 1: Standard lunch request with 3 thematic menus and 4 courses
    assert any(
        kw in raw_text for kw in ["thematic", "course", "menu", "standard"]
    ), "Dataset missing Scenario 1 (3 thematic 4-course menus)"

    # Scenario 2: Active allergies (peanuts, shellfish, vegetarian) & filtering notes
    assert "peanut" in raw_text, "Dataset missing Scenario 2 dietary allergen (peanut)"
    assert any(
        kw in raw_text for kw in ["shellfish", "vegetarian", "dietary", "filter"]
    ), "Dataset missing Scenario 2 dietary constraints (shellfish/vegetarian/filtering)"

    # Scenario 3: Pure dietary update without booking proposal
    assert any(
        kw in raw_text for kw in ["celiac", "gluten", "allergy", "preference"]
    ), "Dataset missing Scenario 3 (pure dietary preference update)"

    # Scenario 4: Booking confirmation with catering selection
    assert any(
        kw in raw_text for kw in ["book", "booking", "confirmed", "bk_"]
    ), "Dataset missing Scenario 4 (booking with catering confirmation)"

    # Scenario 5: Offline / local fallback
    assert any(
        kw in raw_text for kw in ["fallback", "offline", "local", "mcp"]
    ), "Dataset missing Scenario 5 (offline/local dataset fallback)"


# ==============================================================================
# 2. Config Verification (eval_config.yaml)
# ==============================================================================


def test_eval_config_exists_and_registers_catering_metrics() -> None:
    """Validates eval_config.yaml registers dietary_filtering and menu_structure_compliance."""
    assert EVAL_CONFIG_FILE.exists(), f"eval_config.yaml not found at {EVAL_CONFIG_FILE}"

    with open(EVAL_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert isinstance(config, dict), "eval_config.yaml must parse to a dictionary"
    assert "custom_metrics" in config, "eval_config.yaml missing 'custom_metrics'"

    custom_metrics = config["custom_metrics"]
    assert isinstance(custom_metrics, list), "'custom_metrics' must be a list"

    metric_names = {m.get("name") for m in custom_metrics if isinstance(m, dict)}

    assert "dietary_filtering" in metric_names, (
        f"'dietary_filtering' not registered in eval_config.yaml custom_metrics. Found: {metric_names}"
    )
    assert "menu_structure_compliance" in metric_names, (
        f"'menu_structure_compliance' not registered in eval_config.yaml custom_metrics. Found: {metric_names}"
    )

    # Verify custom function file mappings point to catering_eval.py
    for metric in custom_metrics:
        if metric.get("name") in ("dietary_filtering", "menu_structure_compliance"):
            custom_file = metric.get("custom_function_file") or metric.get("file")
            assert custom_file == "catering_eval.py", (
                f"Metric {metric.get('name')} should point to 'catering_eval.py', got '{custom_file}'"
            )


# ==============================================================================
# 3. Custom Evaluators (catering_eval.py)
# ==============================================================================


@pytest.fixture
def catering_eval():
    """Fixture providing the catering_eval module."""
    return _load_catering_eval_module()


@pytest.fixture
def valid_three_menu_response() -> str:
    """A mock proposal response containing 3 thematic menus with 4 courses each."""
    return (
        "# OmniChef Alignment Lunch\n\n"
        "**Strategic Rationale**: Cross-functional launch alignment.\n\n"
        "### Included Team Members\n"
        "Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai\n\n"
        "### Proposed Catering Menus\n\n"
        "#### Menu 1: Baja Fiesta\n"
        "- **Mains**: Carnitas Taco Platter, Vegan Sweet Potato Enchiladas\n"
        "- **Sides**: Southwest Roasted Corn Salad, Guacamole & Chips\n"
        "- **Beverages**: Mexican Horchata\n"
        "- **Desserts**: Churro Bites with Dulce de Leche\n\n"
        "#### Menu 2: Mediterranean Delight\n"
        "- **Mains**: Chicken Shawarma Plate, Veggie Mezze Platter\n"
        "- **Sides**: Greek Farmer Salad, Hummus & Pita\n"
        "- **Beverages**: Cucumber Mint Detox Water\n"
        "- **Desserts**: Mini Cannoli Trio\n\n"
        "#### Menu 3: Pan-Asian Bistro\n"
        "- **Mains**: Thai Red Curry Chicken, Tofu Fried Rice\n"
        "- **Sides**: Sesame Slaw, Vegetable Spring Rolls\n"
        "- **Beverages**: Matcha Green Tea Latte\n"
        "- **Desserts**: Mango Sticky Rice\n\n"
        "### Dietary Accommodations\n"
        "Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)\n"
    )


# --- dietary_filtering tests ---


def test_dietary_filtering_passing(catering_eval, valid_three_menu_response: str) -> None:
    """Passing response: no prohibited ingredients, accommodation phrasing present."""
    instance = {
        "context": {
            "allergies": ["peanut", "shellfish"],
            "preferences": ["vegetarian"],
        },
        "response": valid_three_menu_response,
    }

    # Test invoking as dietary_filtering(instance, response) and dietary_filtering(instance)
    res1 = catering_eval.dietary_filtering(instance, valid_three_menu_response)
    res2 = catering_eval.dietary_filtering(instance)

    for res in (res1, res2):
        assert isinstance(res, dict), "Evaluator must return a dict"
        assert "score" in res, "Evaluator result must contain 'score'"
        assert isinstance(res["score"], (int, float)), "Score must be numeric"
        assert res["score"] == pytest.approx(1.0), f"Expected 1.0 for passing response, got {res['score']}"


def test_dietary_filtering_fails_on_prohibited_ingredient(catering_eval, valid_three_menu_response: str) -> None:
    """Fails when prohibited allergen or non-compliant item appears in response."""
    contaminated_response = valid_three_menu_response.replace(
        "Southwest Roasted Corn Salad",
        "Thai Spicy Peanut Salad with Crushed Peanuts",
    )
    instance = {
        "context": {
            "allergies": ["peanut"],
        },
        "response": contaminated_response,
    }

    res = catering_eval.dietary_filtering(instance, contaminated_response)
    assert isinstance(res, dict)
    assert res["score"] < 1.0, f"Expected penalized score for allergen contamination, got {res['score']}"
    assert res["score"] >= 0.0, "Score must not be negative"


def test_dietary_filtering_fails_on_missing_accommodation_note(catering_eval, valid_three_menu_response: str) -> None:
    """Fails or is penalized when explicit accommodation note is missing."""
    no_note_response = valid_three_menu_response.replace(
        "Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)",
        "",
    )
    instance = {
        "context": {
            "allergies": ["peanut"],
            "preferences": ["vegetarian"],
        },
        "response": no_note_response,
    }

    res = catering_eval.dietary_filtering(instance, no_note_response)
    assert isinstance(res, dict)
    assert res["score"] < 1.0, f"Expected penalty when accommodation note is absent, got {res['score']}"


def test_dietary_filtering_no_constraints_active(catering_eval, valid_three_menu_response: str) -> None:
    """When no dietary constraints are active, filtering requirement is satisfied."""
    instance = {
        "context": {
            "allergies": [],
            "preferences": [],
        },
        "response": valid_three_menu_response,
    }

    res = catering_eval.dietary_filtering(instance, valid_three_menu_response)
    assert res["score"] == pytest.approx(1.0)


def test_dietary_filtering_score_bounds_and_determinism(catering_eval) -> None:
    """Evaluator must always return deterministic scores bounded in [0.0, 1.0]."""
    instance = {
        "context": {"allergies": ["shellfish"]},
        "response": "Shrimp Cocktail with Shellfish Bisque",
    }
    res_a = catering_eval.dietary_filtering(instance, instance["response"])
    res_b = catering_eval.dietary_filtering(instance, instance["response"])

    assert res_a == res_b, "Evaluator must be deterministic"
    assert 0.0 <= res_a["score"] <= 1.0, f"Score out of bounds [0.0, 1.0]: {res_a['score']}"


# --- menu_structure_compliance tests ---


def test_menu_structure_compliance_passing(catering_eval, valid_three_menu_response: str) -> None:
    """Passing response: exactly 3 menus, each with mains, sides, beverages, and desserts."""
    instance = {"response": valid_three_menu_response}

    res1 = catering_eval.menu_structure_compliance(instance, valid_three_menu_response)
    res2 = catering_eval.menu_structure_compliance(instance)

    for res in (res1, res2):
        assert isinstance(res, dict)
        assert "score" in res
        assert res["score"] == pytest.approx(1.0), f"Expected 1.0 for valid 3-menu proposal, got {res['score']}"


def test_menu_structure_compliance_fails_on_fewer_than_three_menus(catering_eval) -> None:
    """Fails when response offers fewer than 3 menus."""
    two_menu_response = (
        "### Proposed Catering Menus\n\n"
        "#### Menu 1: Baja Fiesta\n"
        "- Mains: Tacos\n- Sides: Corn\n- Beverages: Water\n- Desserts: Churros\n\n"
        "#### Menu 2: Mediterranean Delight\n"
        "- Mains: Shawarma\n- Sides: Salad\n- Beverages: Tea\n- Desserts: Baklava\n"
    )
    instance = {"response": two_menu_response}
    res = catering_eval.menu_structure_compliance(instance, two_menu_response)
    assert res["score"] < 1.0, f"Expected penalty for 2 menus instead of 3, got {res['score']}"


def test_menu_structure_compliance_fails_on_more_than_three_menus(catering_eval) -> None:
    """Fails when response offers more than 3 menus."""
    four_menu_response = (
        "### Proposed Catering Menus\n\n"
        "#### Menu 1: Baja Fiesta\n- Mains: Tacos\n- Sides: Corn\n- Beverages: Water\n- Desserts: Churros\n\n"
        "#### Menu 2: Mediterranean\n- Mains: Shawarma\n- Sides: Salad\n- Beverages: Tea\n- Desserts: Baklava\n\n"
        "#### Menu 3: Pan-Asian\n- Mains: Curry\n- Sides: Slaw\n- Beverages: Chai\n- Desserts: Mochi\n\n"
        "#### Menu 4: Classic Deli\n- Mains: Sandwiches\n- Sides: Chips\n- Beverages: Soda\n- Desserts: Cookies\n"
    )
    instance = {"response": four_menu_response}
    res = catering_eval.menu_structure_compliance(instance, four_menu_response)
    assert res["score"] < 1.0, f"Expected penalty for 4 menus instead of 3, got {res['score']}"


def test_menu_structure_compliance_fails_on_missing_course(catering_eval) -> None:
    """Fails when a menu is missing one of the required 4 courses (mains, sides, beverages, desserts)."""
    missing_desserts_response = (
        "### Proposed Catering Menus\n\n"
        "#### Menu 1: Baja Fiesta\n- Mains: Tacos\n- Sides: Corn\n- Beverages: Water\n\n"  # Missing Desserts
        "#### Menu 2: Mediterranean\n- Mains: Shawarma\n- Sides: Salad\n- Beverages: Tea\n- Desserts: Baklava\n\n"
        "#### Menu 3: Pan-Asian\n- Mains: Curry\n- Sides: Slaw\n- Beverages: Chai\n- Desserts: Mochi\n"
    )
    instance = {"response": missing_desserts_response}
    res = catering_eval.menu_structure_compliance(instance, missing_desserts_response)
    assert res["score"] < 1.0, f"Expected penalty for missing course, got {res['score']}"


def test_menu_structure_compliance_empty_or_malformed(catering_eval) -> None:
    """Evaluator handles empty, malformed, or irrelevant text gracefully without crashing."""
    instance = {"response": ""}
    res_empty = catering_eval.menu_structure_compliance(instance, "")
    assert isinstance(res_empty, dict)
    assert res_empty["score"] == pytest.approx(0.0)

    instance_garbage = {"response": "Hello world, what time is the meeting?"}
    res_garbage = catering_eval.menu_structure_compliance(instance_garbage, instance_garbage["response"])
    assert isinstance(res_garbage, dict)
    assert res_garbage["score"] == pytest.approx(0.0)


def test_menu_structure_compliance_score_bounds_and_determinism(catering_eval, valid_three_menu_response: str) -> None:
    """Evaluator returns deterministic scores strictly bounded within [0.0, 1.0]."""
    instance = {"response": valid_three_menu_response}
    res_a = catering_eval.menu_structure_compliance(instance, valid_three_menu_response)
    res_b = catering_eval.menu_structure_compliance(instance, valid_three_menu_response)

    assert res_a == res_b, "Evaluator must be deterministic"
    assert 0.0 <= res_a["score"] <= 1.0, f"Score out of bounds [0.0, 1.0]: {res_a['score']}"
