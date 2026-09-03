"""Unified Reviewer ADK Agent definition."""

from google.adk.apps.app import App

try:
    from .workflow import reviewer_workflow, run_reviewer_pipeline
except (ImportError, ValueError):
    from workflow import reviewer_workflow, run_reviewer_pipeline

root_agent = reviewer_workflow
pipeline = run_reviewer_pipeline
app = App(name="reviewer_agent", root_agent=root_agent)

__all__ = ["app", "root_agent", "pipeline", "reviewer_workflow", "run_reviewer_pipeline"]
