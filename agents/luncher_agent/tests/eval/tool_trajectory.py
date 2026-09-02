"""Deterministic metric for proposal tool invocation (see eval_config.yaml).

The synthesizer must format its proposal by calling `format_lunch_proposal` exactly once.
Deterministic -- it walks the recorded trace rather than asking a model.
"""

TOOL_NAME = "format_lunch_proposal"


def _iter_function_calls(agent_data):
    for turn in (agent_data or {}).get("turns", []):
        for event in turn.get("events", []):
            content = event.get("content") or {}
            for part in content.get("parts", []) or []:
                call = part.get("function_call") or part.get("functionCall")
                if call and call.get("name"):
                    yield call


def evaluate(instance):
    calls = list(_iter_function_calls(instance.get("agent_data")))
    names = [call["name"] for call in calls]
    count = names.count(TOOL_NAME)

    if count == 1:
        return {"score": 1, "explanation": f"{TOOL_NAME} called once. All calls: {names}."}
    if count == 0:
        return {
            "score": 0,
            "explanation": (
                f"{TOOL_NAME} was never called, so no proposal was formatted."
                f" Calls seen: {names or 'none'}."
            ),
        }
    return {
        "score": 0,
        "explanation": f"{TOOL_NAME} called {count} times; duplicate calls. Calls: {names}.",
    }
