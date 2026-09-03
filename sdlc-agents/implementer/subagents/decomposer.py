import os
from google.antigravity import Agent, LocalAgentConfig, types
from google.antigravity.hooks import policy
from . import load_prompt

def get_decomposer_config(hooks=None) -> LocalAgentConfig:
    use_vertex = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        or bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    )
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GOOGLE_GENAI_LOCATION", "global")
    model_name = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.7-flash")
    api_key = os.environ.get("GEMINI_API_KEY")

    return LocalAgentConfig(
        system_instructions=load_prompt("decomposer"),
        capabilities=types.CapabilitiesConfig(
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
        ),
        policies=[
            policy.deny("run_command"),
            policy.deny("ask_question"),
            policy.allow_all(),
        ],
        hooks=hooks,
        vertex=use_vertex if not api_key else False,
        project=project if use_vertex and not api_key else None,
        location=location if use_vertex and not api_key else None,
        model=model_name if use_vertex and not api_key else None,
        api_key=api_key,
    )

def create_decomposer_agent(hooks=None) -> Agent:
    return Agent(config=get_decomposer_config(hooks=hooks))
