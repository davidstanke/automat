"""Unified Reviewer ADK Agent definition."""

from google.adk.apps.app import App

try:
    from .workflow import reviewer_workflow
except (ImportError, ValueError):
    from workflow import reviewer_workflow

root_agent = reviewer_workflow
app = App(name="reviewer_agent", root_agent=root_agent)

__all__ = ["app", "root_agent", "reviewer_workflow"]
