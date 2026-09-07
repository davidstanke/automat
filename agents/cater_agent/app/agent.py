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

import logging
import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.google_llm import Gemini
from google.genai.types import HttpRetryOptions, ThinkingConfig, ThinkingLevel

from .tools import get_catering_menus

# Load environment variables
load_dotenv(override=True)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

cater_retry_policy = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    http_status_codes=[429, 500, 503],
)

logger = logging.getLogger(__name__)

MODEL_LOCATION = os.getenv("GOOGLE_GENAI_LOCATION", "global")
# Pinned version. Override via GOOGLE_GENAI_MODEL. Served from global endpoint.
MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.7-flash")

logger.info("Using Gemini model '%s' in location '%s'", MODEL, MODEL_LOCATION)

root_agent = Agent(
    model=Gemini(
        model=MODEL,
        thinking_config=ThinkingConfig(thinking_level=ThinkingLevel.MINIMAL),
        retry_options=cater_retry_policy,
        client_kwargs={"location": MODEL_LOCATION},
    ),
    name="cater_agent",
    description="Proposes curated in-house catering menu options (dishes, sides, desserts, beverages) for team lunch meetings.",
    instruction=(
        "You are the Catering Coordinator Agent for GeniCo. Your purpose is to propose curated in-house "
        "catering menu options to serve at team lunch meetings.\n\n"
        "Your available tool:\n"
        "1. 'get_catering_menus' - Returns exactly 3 curated in-house mock menus with their items.\n\n"
        "CRITICAL BEHAVIOR RULES:\n"
        "- ALWAYS call 'get_catering_menus' to retrieve the 3 curated mock menu options:\n"
        "  1. Menu 1: Buffalo Chicken Wrap Platter (buffalo chicken wrap, mixed greens salad, chocolate cookie, assorted sodas)\n"
        "  2. Menu 2: Veggie Taco Fiesta (veggie tacos, snow pea salad, apple tartlets, tea service)\n"
        "  3. Menu 3: Indian Curry Feast (lamb vindaloo, spiced cauliflower, naan, orange-mint spa water)\n"
        "- Structure your output with a distinct '### Catering Menu Options' Markdown section.\n"
        "- Present all 3 menus with their deterministic identifier (menu_1, menu_2, menu_3), title, and complete list of items.\n"
        "- Include guidance explaining that meeting organizers can confirm their preferred menu option when booking a time slot.\n"
        "- DO NOT execute any external network calls or database queries."
    ),
    tools=[get_catering_menus],
)

app = App(
    root_agent=root_agent,
    name="app",
)
