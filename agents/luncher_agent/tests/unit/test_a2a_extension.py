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

"""Tests for A2A capabilities and event routing (app.app_utils.a2a)."""

from unittest.mock import MagicMock
from app.app_utils import a2a as a2a_mod



def test_only_synthesizer_speaks_withholds_intermediate_subagent_turns() -> None:
    events_passed = []

    def fake_converter(event, *args, **kwargs):
        events_passed.append(event)
        return ["converted"]

    filter_fn = a2a_mod._only_synthesizer_speaks(fake_converter)

    # Sub-agent event with text
    sub_event = MagicMock()
    sub_event.author = "strategy_agent"
    part = MagicMock()
    part.text = "Here is corporate strategy..."
    sub_event.content.parts = [part]

    result = filter_fn(sub_event)
    assert result == []
    assert len(events_passed) == 0

    # Synthesizer event with text
    synth_event = MagicMock()
    synth_event.author = "lunch_synthesizer"
    part2 = MagicMock()
    part2.text = "Here is the team lunch proposal..."
    synth_event.content.parts = [part2]

    result2 = filter_fn(synth_event)
    assert result2 == ["converted"]
    assert len(events_passed) == 1
