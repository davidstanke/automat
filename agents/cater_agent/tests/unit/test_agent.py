from app.agent import app, root_agent
from google.adk.agents import Agent
from google.adk.apps import App


def test_root_agent_initialization() -> None:
    assert isinstance(root_agent, Agent)
    assert root_agent.name == "cater_agent"
    assert "Catering Agent" in root_agent.instruction
    assert "get_catering_menus" in [t.__name__ for t in root_agent.tools]


def test_app_initialization() -> None:
    assert isinstance(app, App)
    assert app.name == "app"
    assert app.root_agent is root_agent
