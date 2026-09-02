"""SDLC Implementer Agent definition using Antigravity SDK."""

try:
    from .workflow import run_implementer_pipeline, implementer_workflow, implementer_pipeline
except (ImportError, ValueError):
    from workflow import run_implementer_pipeline, implementer_workflow, implementer_pipeline

root_agent = implementer_pipeline
pipeline = implementer_pipeline

__all__ = ["root_agent", "pipeline", "run_implementer_pipeline", "implementer_workflow", "implementer_pipeline"]
