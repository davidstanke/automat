"""FastAPI server for the Reviewer ADK Agent with A2A and Cloud Run support."""

import contextlib
import os
from pathlib import Path
import sys
from typing import Any, AsyncIterator, Dict, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Ensure repo root and package path in sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(repo_root)

load_dotenv()

from google.adk.runners import InMemoryRunner
from google.genai import types

try:
    from .agent import app as adk_app, root_agent
except (ImportError, ValueError):
    from agent import app as adk_app, root_agent


class TaskRequest(BaseModel):
    pr_number: Optional[Any] = Field(default=None, description="GitHub Pull Request Number (e.g. 42)")
    session_id: Optional[str] = Field(default=None, description="Optional session ID")
    repo_url: Optional[str] = Field(default=None, description="Git clone URL (e.g. https://github.com/owner/repo.git)")
    branch: Optional[str] = Field(default=None, description="Target feature branch name")
    base_branch: Optional[str] = Field(default="main", description="Target base branch for Pull Request")
    github_token: Optional[str] = Field(default=None, description="Ephemeral GitHub token for cloning and posting reviews")


class A2AMessageRequest(BaseModel):
    message: str = Field(..., description="Prompt or message content")
    session_id: Optional[str] = Field(default=None, description="Optional session ID")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runner = InMemoryRunner(app=adk_app)
    app.state.runner = runner
    app.state.agent_name = "reviewer_agent"
    print(f"[Reviewer Server] Initialized runner for {adk_app.name}")
    yield


app = FastAPI(
    title="SDLC Pull Request Reviewer Agent Service",
    description="Automated code review & maintainability agent workflow service",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": "reviewer_agent",
        "workflow": root_agent.name,
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": "reviewer_agent",
        "description": "SDLC Pull Request Reviewer Agent Service",
    }


@app.get("/.well-known/agent.json")
async def agent_card() -> Dict[str, Any]:
    """A2A Agent Card for agent discovery."""
    return {
        "name": "reviewer_agent",
        "description": "Automated SDLC Pull Request Reviewer Agent",
        "version": "0.1.0",
        "capabilities": ["sdlc", "code-review", "clean-code", "maintainability", "defect-inspection"],
        "endpoints": {
            "a2a": "/a2a/reviewer_agent",
            "health": "/healthz",
            "tasks": "/tasks",
        },
    }


async def stream_task_events(req: TaskRequest) -> AsyncIterator[str]:
    """Streams workflow execution events as plain text SSE data lines."""
    runner: InMemoryRunner = app.state.runner
    user_id = "a2a_caller"
    session = await runner.session_service.create_session(
        app_name=adk_app.name,
        user_id=user_id,
    )

    user_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=req.model_dump_json())],
    )

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=user_content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        for line in part.text.splitlines():
                            yield f"data: {line}\n"
                        yield "\n"
    except Exception as e:
        yield f"data: [Error] Execution failed: {str(e)}\n\n"


@app.post("/tasks")
@app.post("/a2a/reviewer_agent")
async def execute_task(req: TaskRequest, request: Request):
    """Executes the reviewer workflow on a Pull Request with SSE streaming."""
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header and "text/event-stream" not in accept_header:
        # Non-streaming JSON response fallback
        runner: InMemoryRunner = app.state.runner
        user_id = "a2a_caller"
        session = await runner.session_service.create_session(
            app_name=adk_app.name,
            user_id=user_id,
        )

        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=req.model_dump_json())],
        )

        events_output = []
        final_summary = ""
        status = "completed"

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=user_content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            events_output.append(part.text)
                if isinstance(event.output, dict):
                    if "summary" in event.output:
                        final_summary = event.output["summary"]
                    if "status" in event.output:
                        status = event.output["status"]
        except Exception as e:
            status = "error"
            events_output.append(f"Execution failed: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "error": str(e),
                    "events": events_output,
                },
            )

        return {
            "status": status,
            "summary": final_summary or "\n".join(events_output),
            "events": events_output,
        }

    # Default: Stream SSE in real time
    return StreamingResponse(
        stream_task_events(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8100"))
    uvicorn.run("server:app", host=host, port=port, reload=True)
