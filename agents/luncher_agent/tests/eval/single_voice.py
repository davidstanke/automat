"""Deterministic metric for `single_voice` (see eval_config_a2a.yaml).

Grades what an A2A client is actually handed. Only `lunch_synthesizer` addresses
the user; the gatherers feed it, and each of their answers is an event of its
own. Unwithheld they arrive as further text parts, so one turn narrates itself
several times and describes the booking twice.

Every author's contribution is a separate text part, so counting them measures
the delivered result without attributing authorship -- which the A2A payload
does not carry.

This grades traces captured over A2A (`05-run-evals.sh <agent> --a2a`). The ADK
REST path does no withholding, so grading its traces scores 0 whatever the agent
does.
"""


def _parts(response) -> list:
    if isinstance(response, list):
        return [part for item in response for part in _parts(item)]
    if isinstance(response, dict):
        inner = response.get("response")
        if isinstance(inner, (dict, list)):
            return _parts(inner)
        return [part for part in response.get("parts") or [] if isinstance(part, dict)]
    return []


def _is_text(part) -> bool:
    if part.get("kind") == "text":
        return bool((part.get("text") or "").strip())
    return bool((part.get("text") or "").strip()) and "data" not in part


def evaluate(instance):
    parts = _parts(instance.get("response"))
    texts = [part for part in parts if _is_text(part)]

    if not texts:
        return {"score": 0, "explanation": f"No text part in {len(parts)} part(s)."}
    if len(texts) > 1:
        preview = " | ".join((t.get("text") or "")[:60] for t in texts[:3])
        return {
            "score": 0,
            "explanation": (
                f"{len(texts)} text parts delivered; only the synthesizer should"
                f" speak. Openings: {preview}"
            ),
        }
    return {
        "score": 1,
        "explanation": "One text part delivered from the synthesizer.",
    }
