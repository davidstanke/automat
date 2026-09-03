# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests verifying Cater Agent foundation and service scaffolding.

Covers:
- pyproject.toml specification (name, python requires, dependencies, pytest config).
- Dockerfile and containerization configuration matching Agent Runtime standards.
- main.py entrypoint, default port 8083, and PORT env override.
- FastAPI app initialization, telemetry setup, and route mounting without network calls.
- Lifespan Runner establishment and A2A route mounting.
- app_utils modular architecture and contract exports.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import runpy
import sys
import tomllib
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
import pytest


AGENT_DIR = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture: Mock external cloud services to guarantee zero network calls
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_external_network_calls(monkeypatch: pytest.MonkeyPatch):
    """Enforce complete offline operation by mocking GCP auth and logging."""
    mock_creds = MagicMock()
    mock_creds.project_id = "test-project"

    try:
        import google.auth

        monkeypatch.setattr(
            google.auth, "default", lambda *args, **kwargs: (mock_creds, "test-project")
        )
    except ImportError:
        pass

    try:
        from google.cloud import logging as google_cloud_logging

        mock_logging_client = MagicMock()
        monkeypatch.setattr(
            google_cloud_logging, "Client", lambda *args, **kwargs: mock_logging_client
        )
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# 1. pyproject.toml Configuration Tests
# ---------------------------------------------------------------------------
def test_pyproject_toml_configuration() -> None:
    """Verify pyproject.toml specifies correct metadata, constraints, and dependencies."""
    pyproject_file = AGENT_DIR / "pyproject.toml"
    assert pyproject_file.is_file(), f"Expected {pyproject_file} to exist"

    with open(pyproject_file, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    assert project.get("name") == "cater-agent", "Project name must be 'cater-agent'"
    assert project.get("requires-python") == ">=3.12, <3.14", (
        "Python version requirement must be '>=3.12, <3.14'"
    )

    dependencies = project.get("dependencies", [])
    assert any(dep.startswith("google-adk[a2a,eval,gcp,otel-gcp]") for dep in dependencies), (
        "Dependencies must include 'google-adk[a2a,eval,gcp,otel-gcp]>=2.5.0,<3.0.0'"
    )
    assert any(dep.startswith("mcp") for dep in dependencies), (
        "Dependencies must include 'mcp>=1.0.0,<2.0.0'"
    )
    assert any(dep.startswith("bigquery-mcp") for dep in dependencies), (
        "Dependencies must include 'bigquery-mcp>=0.1.0'"
    )
    assert any(dep.startswith("uvicorn") for dep in dependencies), (
        "Dependencies must include 'uvicorn'"
    )
    assert any(dep.startswith("fastapi") for dep in dependencies), (
        "Dependencies must include 'fastapi'"
    )
    assert any(dep.startswith("pydantic") for dep in dependencies), (
        "Dependencies must include 'pydantic'"
    )

    # Pytest configuration
    pytest_config = (
        data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    )
    assert pytest_config.get("pythonpath") == ".", (
        "tool.pytest.ini_options.pythonpath must be '.'"
    )


# ---------------------------------------------------------------------------
# 2. Containerization (Dockerfile & .dockerignore) Tests
# ---------------------------------------------------------------------------
def test_dockerfile_and_dockerignore_configuration() -> None:
    """Verify Dockerfile and .dockerignore conform to Agent Runtime standards."""
    dockerfile_path = AGENT_DIR / "Dockerfile"
    assert dockerfile_path.is_file(), f"Expected {dockerfile_path} to exist"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "python:3.12-slim" in content, "Dockerfile must use python:3.12-slim base image"
    assert "uv" in content, "Dockerfile must install and use uv"
    assert "uv sync" in content, "Dockerfile must execute 'uv sync'"
    assert "8080" in content, "Dockerfile must reference container port 8080"
    assert "app.fast_api_app:app" in content, (
        "Dockerfile CMD must serve 'app.fast_api_app:app'"
    )

    dockerignore_path = AGENT_DIR / ".dockerignore"
    assert dockerignore_path.is_file(), f"Expected {dockerignore_path} to exist"

    dockerignore_content = dockerignore_path.read_text(encoding="utf-8")
    assert ".venv" in dockerignore_content, ".dockerignore must ignore .venv"
    assert "tests" in dockerignore_content, ".dockerignore must ignore tests"
    assert "__pycache__" in dockerignore_content, ".dockerignore must ignore __pycache__"


def test_gitignore_configuration() -> None:
    """Verify .gitignore exists and ignores local virtual environments and bytecode."""
    gitignore_path = AGENT_DIR / ".gitignore"
    assert gitignore_path.is_file(), f"Expected {gitignore_path} to exist"

    content = gitignore_path.read_text(encoding="utf-8")
    assert ".venv" in content, ".gitignore must ignore .venv"
    assert "__pycache__" in content or "*.pyc" in content, ".gitignore must ignore bytecode"


# ---------------------------------------------------------------------------
# 3. main.py Port & Entrypoint Tests
# ---------------------------------------------------------------------------
def test_main_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify main.py defaults to port 8083 when PORT environment variable is not set."""
    monkeypatch.delenv("PORT", raising=False)

    if "main" in sys.modules:
        del sys.modules["main"]

    main_mod = importlib.import_module("main")
    assert main_mod.port == 8083, "Default port must be 8083"
    assert os.environ.get("PORT") == "8083", "main.py must set os.environ['PORT'] to '8083'"


def test_main_port_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify main.py respects PORT environment variable overrides."""
    monkeypatch.setenv("PORT", "9099")

    if "main" in sys.modules:
        del sys.modules["main"]

    main_mod = importlib.import_module("main")
    assert main_mod.port == 9099, "Port must respect PORT environment variable"
    assert os.environ.get("PORT") == "9099"


def test_main_uvicorn_execution_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify executing main.py as script invokes uvicorn.run with default port 8083."""
    monkeypatch.delenv("PORT", raising=False)
    main_path = str(AGENT_DIR / "main.py")

    with patch("uvicorn.run") as mock_run:
        runpy.run_path(main_path, run_name="__main__")
        mock_run.assert_called_once_with(
            "app.fast_api_app:app",
            host="0.0.0.0",
            port=8083,
            reload=True,
        )


def test_main_uvicorn_execution_custom_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify executing main.py as script invokes uvicorn.run with custom PORT env."""
    monkeypatch.setenv("PORT", "8888")
    main_path = str(AGENT_DIR / "main.py")

    with patch("uvicorn.run") as mock_run:
        runpy.run_path(main_path, run_name="__main__")
        mock_run.assert_called_once_with(
            "app.fast_api_app:app",
            host="0.0.0.0",
            port=8888,
            reload=True,
        )


# ---------------------------------------------------------------------------
# 4. FastAPI App Creation & Route Mounting Tests
# ---------------------------------------------------------------------------
def test_fastapi_app_creation_and_routes() -> None:
    """Verify FastAPI application instance is created with expected routes and feedback endpoint."""
    fast_api_module = importlib.import_module("app.fast_api_app")
    app = getattr(fast_api_module, "app", None)
    assert isinstance(app, FastAPI), "app.fast_api_app:app must be a FastAPI instance"

    route_paths = [route.path for route in app.routes]

    # Verify feedback route exists
    assert "/feedback" in route_paths, "FastAPI app must mount /feedback endpoint"

    # Verify feedback route supports POST method
    feedback_route = next(r for r in app.routes if r.path == "/feedback")
    assert "POST" in feedback_route.methods, "/feedback endpoint must accept POST requests"


def test_telemetry_functions_present() -> None:
    """Verify telemetry initialization functions are defined and configurable."""
    telemetry_mod = importlib.import_module("app.app_utils.telemetry")
    assert hasattr(telemetry_mod, "setup_telemetry"), "setup_telemetry must be defined"
    assert hasattr(telemetry_mod, "setup_agent_engine_telemetry"), (
        "setup_agent_engine_telemetry must be defined"
    )

    # Calling setup_telemetry without bucket should complete cleanly without network calls
    with patch.dict(os.environ, {"LOGS_BUCKET_NAME": ""}, clear=False):
        bucket = telemetry_mod.setup_telemetry()
        assert bucket == ""


def test_app_utils_modules_exist_and_importable() -> None:
    """Verify required app_utils helper modules are importable and define their interfaces."""
    # services
    services_mod = importlib.import_module("app.app_utils.services")
    assert hasattr(services_mod, "SESSION_SERVICE_URI")
    assert hasattr(services_mod, "ARTIFACT_SERVICE_URI")
    assert hasattr(services_mod, "get_session_service")
    assert hasattr(services_mod, "get_artifact_service")

    # typing
    typing_mod = importlib.import_module("app.app_utils.typing")
    assert hasattr(typing_mod, "Feedback")

    # a2a
    a2a_mod = importlib.import_module("app.app_utils.a2a")
    assert hasattr(a2a_mod, "attach_a2a_routes")

    # reasoning_engine_adapter
    rea_mod = importlib.import_module("app.app_utils.reasoning_engine_adapter")
    assert hasattr(rea_mod, "attach_reasoning_engine_routes")

    # genai_transport
    genai_mod = importlib.import_module("app.app_utils.genai_transport")
    assert genai_mod is not None


# ---------------------------------------------------------------------------
# 5. Lifespan Runner Management & A2A Route Mounting Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lifespan_runner_establishment() -> None:
    """Verify lifespan initializes Runner, stores it on app.state, and attaches A2A routes."""
    fast_api_module = importlib.import_module("app.fast_api_app")
    app = getattr(fast_api_module, "app")
    lifespan_fn = getattr(fast_api_module, "lifespan", None)

    assert lifespan_fn is not None, "app.fast_api_app must define a lifespan context manager"

    mock_agent_mod = MagicMock()
    mock_agent_mod.app.name = "cater_agent"
    mock_agent_mod.root_agent = MagicMock()

    agent_modules = {"app.agent": sys.modules.get("app.agent", mock_agent_mod)}

    with patch.dict(sys.modules, agent_modules):
        with patch("app.fast_api_app.attach_a2a_routes", new_callable=AsyncMock) as mock_attach:
            async with lifespan_fn(app):
                assert hasattr(app.state, "runner"), "Lifespan must set app.state.runner"
                assert app.state.runner is not None
                assert hasattr(app.state, "agent_app_name"), "Lifespan must set app.state.agent_app_name"

                mock_attach.assert_awaited_once()
                called_kwargs = mock_attach.await_args.kwargs
                assert "agent" in called_kwargs
                assert "runner" in called_kwargs
                assert "task_store" in called_kwargs
                assert "rpc_path" in called_kwargs


@pytest.mark.asyncio
async def test_attach_a2a_routes_mounts_agent_card() -> None:
    """Verify attach_a2a_routes mounts the agent card route under the specified rpc_path."""
    from app.app_utils.a2a import attach_a2a_routes
    from a2a.server.tasks import InMemoryTaskStore

    test_app = FastAPI()
    fake_agent = MagicMock()
    fake_agent.name = "cater_agent"
    fake_runner = MagicMock()

    # Avoid external URL resolution dependencies
    with patch("app.app_utils.a2a._resolve_app_url", return_value="http://localhost:8083"):
        await attach_a2a_routes(
            test_app,
            agent=fake_agent,
            runner=fake_runner,
            task_store=InMemoryTaskStore(),
            rpc_path="/a2a/app",
        )

    mounted_paths = [route.path for route in test_app.routes]
    expected_agent_card_path = "/a2a/app/.well-known/agent-card.json"
    assert expected_agent_card_path in mounted_paths, (
        f"Expected {expected_agent_card_path} to be mounted in routes: {mounted_paths}"
    )
