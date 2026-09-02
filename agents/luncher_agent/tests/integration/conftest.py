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

"""Sub-agent servers for the integration tests.

The orchestrator resolves the strategy and scheduling agents over A2A, so both
have to be serving before any test runs -- including the in-process ones in
test_agent.py, which never touch the orchestrator's own HTTP server.
"""

import logging
import os
import subprocess
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from requests.exceptions import RequestException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sessions would otherwise be written to the deployed agent's
# Agent Engine. Popped before anything imports app.app_utils.services, whose
# builders are cached on first call. scripts/06-run-evals.sh does the same.
os.environ.pop("GOOGLE_CLOUD_AGENT_ENGINE_ID", None)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS_DIR = os.path.dirname(AGENT_DIR)

# The card path carries the ADK App name, which is "app" for both sub-agents.
SUB_AGENTS = (("strat_agent", 8081), ("sched_agent", 8082))


def sub_agent_card_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/a2a/app/.well-known/agent-card.json"


def log_output(pipe: Any, log_func: Any) -> None:
    """Log the output from the given pipe."""
    for line in iter(pipe.readline, ""):
        log_func(line.strip())


def tail_output(process: subprocess.Popen[str], tag: str) -> None:
    """Drain both pipes. An undrained PIPE hides startup tracebacks and fills."""
    threading.Thread(
        target=log_output,
        args=(process.stdout, lambda line: logger.info("[%s] %s", tag, line)),
        daemon=True,
    ).start()
    threading.Thread(
        target=log_output,
        args=(process.stderr, lambda line: logger.error("[%s] %s", tag, line)),
        daemon=True,
    ).start()


def wait_for_url(
    url: str,
    process: subprocess.Popen[str] | None = None,
    timeout: int = 90,
    interval: int = 1,
) -> bool:
    """Poll until the agent card is served (it requires the lifespan to run).

    Watching `process` turns a crash on import into a one-second failure with the
    traceback already logged, instead of a silent wait to the full timeout.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process is not None and process.poll() is not None:
            logger.error("Process exited with %s before serving %s", process.returncode, url)
            return False
        try:
            if requests.get(url, timeout=10).status_code == 200:
                logger.info("Ready: %s", url)
                return True
        except RequestException:
            pass
        time.sleep(interval)
    logger.error("%s did not become ready within %d seconds", url, timeout)
    return False


def sub_agent_python(agent: str) -> str:
    """Each agent has its own venv; luncher's interpreter lacks their deps."""
    python = os.path.join(AGENTS_DIR, agent, ".venv", "bin", "python")
    if not os.path.exists(python):
        pytest.fail(f"No venv for {agent}: run `uv sync` in agents/{agent}")
    return python


def sub_agent_env(agent: str) -> dict[str, str]:
    env = os.environ.copy()
    # Bookings would otherwise be written to the deployed agent's Memory Bank.
    env.pop("GOOGLE_CLOUD_AGENT_ENGINE_ID", None)
    if agent == "sched_agent":
        env.setdefault(
            "BIGQUERY_MCP_COMMAND",
            os.path.join(AGENTS_DIR, agent, "scripts", "mock-bigquery-mcp"),
        )
    return env


def start_sub_agents() -> dict[str, subprocess.Popen[str]]:
    """Start the sub-agents that are not already serving."""
    processes = {}
    for agent, port in SUB_AGENTS:
        if wait_for_url(sub_agent_card_url(port), timeout=2):
            logger.info("%s already serving on port %d", agent, port)
            continue
        process = subprocess.Popen(
            [
                sub_agent_python(agent),
                "-m",
                "uvicorn",
                "app.fast_api_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=os.path.join(AGENTS_DIR, agent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=sub_agent_env(agent),
        )
        tail_output(process, agent)
        processes[agent] = process
    return processes


@pytest.fixture(scope="session", autouse=True)
def sub_agents(request: Any) -> Iterator[None]:
    """Bring the strategy and scheduling agents up for the whole session."""
    started = start_sub_agents()

    def stop_sub_agents() -> None:
        for agent, process in started.items():
            logger.info("Stopping %s", agent)
            process.terminate()
            process.wait()

    request.addfinalizer(stop_sub_agents)

    for agent, port in SUB_AGENTS:
        if not wait_for_url(sub_agent_card_url(port), started.get(agent)):
            pytest.fail(f"{agent} failed to start on port {port}")

    yield
