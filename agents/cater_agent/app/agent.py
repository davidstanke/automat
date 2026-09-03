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

"""Agent definition for the Catering Agent (cater_agent).

Defines the root ADK Agent and App configuring Gemini model, dietary safety
and 4-course menu instructions, and catering tools.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

load_dotenv(override=True)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from .tools import (
    get_dietary_preferences,
    get_thematic_menus,
    record_dietary_preference,
)

logger = logging.getLogger(__name__)

cater_retry_policy = types.HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    http_status_codes=[429, 500, 503],
)

MODEL_LOCATION = os.getenv("GOOGLE_GENAI_LOCATION", "global")
MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.6-flash")

INSTRUCTION = (
    "You are the Catering Coordinator Agent (cater_agent). Your primary responsibility is "
    "to manage team dietary preferences and curate distinct thematic 4-course catering menus "
    "for team lunches.\n\n"
    "Your available tools:\n"
    "1. 'record_dietary_preference' - Stores a team member's dietary allergy, restriction, like, or dislike in persistent memory.\n"
    "2. 'get_dietary_preferences' - Retrieves all recorded dietary preferences for the team.\n"
    "3. 'get_thematic_menus' - Generates exactly 3 distinct thematic catering menus adhering strictly to the 4-course structure and filtered for dietary safety.\n\n"
    "CRITICAL BEHAVIOR RULES:\n"
    "- 4-COURSE MENU STRUCTURE: Every catering menu proposed must strictly contain:\n"
    "  1) 1 to 3 mains (main dishes with name, description, allergens, and dietary labels),\n"
    "  2) 2 to 3 sides (side dishes with name),\n"
    "  3) At least 1 beverage,\n"
    "  4) At least 1 dessert.\n"
    "- THEMATIC ORGANIZATION: Menus must be organized under clear culinary themes (e.g., Baja Fiesta, Mediterranean Delight, Pan-Asian Bistro).\n"
    "- DIETARY SAFETY & ACCOMMODATION: Always check stored dietary preferences and filter out any conflicting allergens or restriction violations. Never propose items containing ingredients that violate active team preferences.\n"
    "- RECORDING PREFERENCES: When a user shares an allergy, dietary restriction, dislike, or like, use 'record_dietary_preference' to store it in memory and confirm the update.\n"
    "- MENU RETRIEVAL: When asked for catering suggestions or menus, use 'get_thematic_menus' to retrieve safe thematic menus and display any active dietary accommodations note."
)

root_agent = Agent(
    model=Gemini(
        model=MODEL,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        retry_options=cater_retry_policy,
        client_kwargs={"location": MODEL_LOCATION},
    ),
    name="cater_agent",
    description="Recommends curated 4-course thematic catering menus and manages team dietary preferences.",
    instruction=INSTRUCTION,
    tools=[
        record_dietary_preference,
        get_dietary_preferences,
        get_thematic_menus,
    ],
)

app = App(
    root_agent=root_agent,
    name="cater_agent",
)

__all__ = [
    "app",
    "root_agent",
]
