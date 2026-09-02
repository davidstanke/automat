"""Local LLM-as-judge for `custom_response_quality` (see eval_config.yaml)."""

import os

from google import genai
from google.genai import types
from pydantic import BaseModel

# Follows the agents' own configuration rather than pinning its own. The model
# they run is served only from the `global` endpoint, and a regional one answers
# 404 "Publisher model ... was not found", which reads as a bad model name.
_MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.6-flash")


def _client() -> genai.Client:
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true":
        return genai.Client(location=os.getenv("GOOGLE_GENAI_LOCATION", "global"))
    return genai.Client()  # AI Studio (GEMINI_API_KEY)


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def evaluate(instance):
    reference = instance.get("reference")
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, relevance, and clarity."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )
    prompt = (
        f"You are an expert QA evaluator for an enterprise AI assistant. {rubric}\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"

    # Held in a local: the client owns the transport, and letting it go out of
    # scope mid-call closes it under the request.
    client = _client()
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,  # deterministic grading
            response_mime_type="application/json",
            response_schema=_Verdict,  # guaranteed schema-valid JSON
        ),
    )
    verdict = response.parsed
    if verdict is None:  # model returned nothing usable
        return {"score": 0, "explanation": response.text or ""}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
