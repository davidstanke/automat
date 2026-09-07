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
from google.adk.models import Gemini
from google.genai import types

# Load environment variables
load_dotenv(override=True)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from .tools import get_catering_menus

cater_retry_policy = types.HttpRetryOptions(
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
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        retry_options=cater_retry_policy,
        client_kwargs={"location": MODEL_LOCATION},
    ),
    name="cater_agent",
    description="Provides catering menu options and food suggestions for team lunch meetings.",
    instruction=(
        "You are the Catering Coordinator Agent for GeniCo team lunch meetings. Your purpose "
        "is to provide catering menu options to serve at lunch meetings.\n\n"
        "Your available tools:\n"
        "1. 'get_catering_menus' - Returns the proposed catering menus for the meeting. "
        "ALWAYS call this tool to retrieve the available mock menus.\n\n"
        "CRITICAL BEHAVIOR RULES:\n"
        "- When queried with a lunch meeting or catering request, ALWAYS call 'get_catering_menus'.\n"
        "- Structure your output under '### Catering Menu Options' listing all 3 mock menus with their items:\n"
        "  1. Menu Option 1: Buffalo Chicken Wrap (buffalo chicken wrap, mixed greens salad, chocolate cookie, assorted sodas)\n"
        "  2. Menu Option 2: Veggie Tacos (veggie tacos, snow pea salad, apple tartlets, tea service)\n"
        "  3. Menu Option 3: Lamb Vindaloo (lamb vindaloo, spiced cauliflower, naan, orange-mint spa water)\n"
        "- Do not perform any external network retrieval or database query."
    ),
    tools=[get_catering_menus],
)

app = App(
    root_agent=root_agent,
    name="app",
)
