"""FastAPI server for the Implementer Agent service with Antigravity SDK and A2A support."""

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

try:
    from .workflow import run_implementer_pipeline
except (ImportError, ValueError):
    from workflow import run_implementer_pipeline


class TaskRequest(BaseModel):
    spec_path: str = Field(..., description="Path to spec directory or spec.md file")
    session_id: Optional[str] = Field(default=None, description="Optional session ID")
    repo_url: Optional[str] = Field(default=None, description="Git clone URL (e.g. https://github.com/owner/repo.git)")
    branch: Optional[str] = Field(default=None, description="Target feature branch name")
    base_branch: Optional[str] = Field(default="main", description="Target base branch for Pull Request")
    github_token: Optional[str] = Field(default=None, description="Ephemeral GitHub token for cloning, pushing, and PR creation")
    create_pr: Optional[bool] = Field(default=True, description="Whether to automatically open a Pull Request upon completion")


class A2AMessageRequest(BaseModel):
    message: str = Field(..., description="Prompt or message content")
    session_id: Optional[str] = Field(default=None, description="Optional session ID")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.agent_name = "implementer_agent"
    print("[Implementer Server] Initialized Implementer Agent service (Antigravity SDK)")
    yield


app = FastAPI(
    title="SDLC Implementer Agent Service",
    description="Automated feature implementation agent service powered by Antigravity SDK",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": "implementer_agent",
        "engine": "antigravity-sdk",
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": "implementer_agent",
        "description": "SDLC Implementer Agent Service (Antigravity SDK)",
    }


@app.get("/.well-known/agent.json")
async def agent_card() -> Dict[str, Any]:
    """A2A Agent Card for agent discovery."""
    return {
        "name": "implementer_agent",
        "description": "Automated SDLC Feature Implementer Agent (Antigravity SDK)",
        "version": "0.2.0",
        "capabilities": ["sdlc", "code-generation", "testing", "decomposition"],
        "endpoints": {
            "a2a": "/a2a/implementer_agent",
            "health": "/healthz",
            "tasks": "/tasks",
        },
    }


async def stream_task_events(req: TaskRequest) -> AsyncIterator[str]:
    """Streams workflow execution events as plain text SSE data lines."""
    try:
        async for event in run_implementer_pipeline(req.model_dump()):
            text = str(event)
            for line in text.splitlines():
                yield f"data: {line}\n"
            yield "\n"
    except Exception as e:
        yield f"data: [Error] Execution failed: {str(e)}\n\n"


@app.post("/tasks")
@app.post("/a2a/implementer_agent")
async def execute_task(req: TaskRequest, request: Request):
    """Executes the implementer workflow on a feature specification with SSE streaming."""
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header and "text/event-stream" not in accept_header:
        # Non-streaming JSON response fallback
        events_output = []
        final_summary = ""
        status = "completed"

        try:
            async for event in run_implementer_pipeline(req.model_dump()):
                text = str(event)
                events_output.append(text)
                if event.output:
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
    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run("server:app", host=host, port=port, reload=True)
