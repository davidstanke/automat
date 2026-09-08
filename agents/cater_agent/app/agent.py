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
    description="Provides catering menu options to serve at lunch meetings by proposing 3 distinct mock menus.",
    instruction=(
        "You are the Catering Agent for GeniCo. Your job is to provide catering menu options "
        "for scheduled team lunch meetings.\n\n"
        "Your available tool:\n"
        "1. 'get_catering_menus' - Returns 3 distinct 4-course mock catering menus from the in-house catering service. "
        "Always call this tool when asked for catering suggestions, menu options, or food for a meeting.\n\n"
        "RULES FOR OUTPUT:\n"
        "1. Always call 'get_catering_menus' to retrieve the official catering menus.\n"
        "2. Present exactly 3 proposed menus with their menu IDs (menu_1, menu_2, menu_3), descriptive names, and "
        "categorized courses (Main, Side, Dessert, Beverage):\n"
        "   - Menu 1: Buffalo Chicken Wrap (buffalo chicken wrap, mixed greens salad, chocolate cookie, assorted sodas)\n"
        "   - Menu 2: Veggie Tacos (veggie tacos, snow pea salad, apple tartlets, tea service)\n"
        "   - Menu 3: Lamb Vindaloo (lamb vindaloo, spiced cauliflower, naan, orange-mint spa water)\n"
        "3. Keep your output clear, structured, and concise to allow seamless downstream proposal synthesis.\n"
        "4. Do not perform any external network retrieval or database queries."
    ),
    tools=[get_catering_menus],
)

app = App(
    root_agent=root_agent,
    name="app",
)
