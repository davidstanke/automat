import os
from typing import Any

try:
    from google.antigravity import Agent, LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    Agent = None
    LocalAgentConfig = None
    types = None
    policy = None

from . import load_prompt


def get_implementer_config() -> Any:
    use_vertex = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        or bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    )
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GOOGLE_GENAI_LOCATION", "global")
    model_name = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.7-flash")
    api_key = os.environ.get("GEMINI_API_KEY")

    if LocalAgentConfig is None or types is None or policy is None:
        return None

    return LocalAgentConfig(
        system_instructions=load_prompt("single_shot_implementer"),
        capabilities=types.CapabilitiesConfig(
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
        ),
        policies=[
            policy.deny("run_command"),
            policy.deny("ask_question"),
            policy.allow_all(),
        ],
        vertex=use_vertex if not api_key else False,
        project=project if use_vertex and not api_key else None,
        location=location if use_vertex and not api_key else None,
        model=model_name if use_vertex and not api_key else None,
        api_key=api_key,
    )


def create_implementer_agent() -> Any:
    if Agent is None:
        raise RuntimeError("google-antigravity SDK is not available in current environment.")
    return Agent(config=get_implementer_config())
