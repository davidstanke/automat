#!/usr/bin/env python3
"""Client CLI for invoking the Reviewer Agent service via A2A."""

import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Optional
from dotenv import load_dotenv
import httpx

load_dotenv()

# Ensure package in sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from port_manager import (
    DEFAULT_HOST,
    find_active_server,
    find_free_port,
    is_reviewer_active,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Invoke the Pull Request Reviewer Agent service (with auto-launch if inactive)."
    )
    parser.add_argument(
        "--pr",
        dest="pr_number",
        default=os.environ.get("PR_NUMBER"),
        help="Pull Request Number to review (e.g. 42).",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("REVIEWER_AGENT_URL") or os.environ.get("REVIEWER_SERVICE_URL"),
        help="Direct URL to reviewer service (e.g. http://127.0.0.1:8100 or Cloud Run URL).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Host for local server discovery/launch (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Fail if local server is not active instead of auto-launching.",
    )
    parser.add_argument(
        "--id-token",
        default=os.environ.get("GCP_ID_TOKEN"),
        help="Google Cloud ID Token for authenticated Cloud Run endpoints.",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token for fetching PR diffs and posting review comments.",
    )
    parser.add_argument(
        "--repo-url",
        default=os.environ.get("REPO_URL"),
        help="Target Git repository clone URL (e.g. https://github.com/owner/repo.git).",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("BRANCH"),
        help="Target branch name.",
    )
    parser.add_argument(
        "--base-branch",
        default=os.environ.get("BASE_BRANCH", "main"),
        help="Target base branch (default: main).",
    )
    return parser.parse_args()


async def ensure_server_url(url_override: Optional[str], host: str, no_auto_start: bool) -> str:
    """Returns an active server URL, launching a local instance if necessary."""
    if url_override:
        clean_url = url_override.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{clean_url}/healthz")
                if resp.status_code == 200:
                    print(f"[Client] Connected to active service at: {clean_url}")
                    return clean_url
        except Exception as e:
            print(f"[Client] Warning: Provided URL {clean_url} did not respond to /healthz: {e}")
            return clean_url
        return clean_url

    # Check for active local server in 8100..8109
    active_port = await find_active_server(host=host)
    if active_port:
        server_url = f"http://{host}:{active_port}"
        print(f"[Client] Found active reviewer agent on port {active_port}: {server_url}")
        return server_url

    if no_auto_start:
        raise RuntimeError("No active reviewer agent found and --no-auto-start was specified.")

    # Find a free port and launch server
    port = find_free_port(host=host)
    server_script = Path(__file__).parent / "server.py"

    print(f"[Client] No active reviewer server found. Launching on port {port}...")

    # Launch uvicorn server in background
    venv_python = Path(sys.executable)
    log_file = Path(__file__).parent / "server.log"
    with open(log_file, "a") as log_fp:
        subprocess.Popen(
            [
                str(venv_python),
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                host,
                "--port",
                str(port),
                "--reload",
            ],
            cwd=str(Path(__file__).parent),
            stdout=log_fp,
            stderr=log_fp,
            start_new_session=True,
        )

    # Poll until ready (up to 15s)
    server_url = f"http://{host}:{port}"
    for _ in range(30):
        await asyncio.sleep(0.5)
        if await is_reviewer_active(port, host):
            print(f"[Client] Server is live and healthy at {server_url} (logs: {log_file})")
            return server_url

    raise TimeoutError(f"Server at {server_url} failed to start within 15 seconds. Check {log_file}")


async def stream_task_request(
    server_url: str,
    pr_number: Optional[str],
    repo_url: Optional[str],
    branch: Optional[str],
    base_branch: str,
    github_token: Optional[str],
    id_token: Optional[str],
):
    """Dispatches review task to server and streams SSE lines."""
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    payload = {
        "pr_number": pr_number,
        "repo_url": repo_url,
        "branch": branch,
        "base_branch": base_branch,
        "github_token": github_token,
    }

    url = f"{server_url}/tasks"
    print(f"[Client] Dispatching PR Review task to: {url} (PR: #{pr_number or 'Local'})")

    timeout = httpx.Timeout(3600.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    print(
                        f"[Client Error] Server returned {response.status_code}: {body.decode()}",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        content = line[6:]
                        print(content)
                    elif line.startswith("data:"):
                        content = line[5:]
                        print(content)
                    elif line.strip() and not line.startswith(":"):
                        print(line)
        except Exception as e:
            print(f"[Client Error] Stream connection error: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    args = parse_args()
    try:
        server_url = asyncio.run(
            ensure_server_url(
                url_override=args.url,
                host=args.host,
                no_auto_start=args.no_auto_start,
            )
        )
        asyncio.run(
            stream_task_request(
                server_url=server_url,
                pr_number=args.pr_number,
                repo_url=args.repo_url,
                branch=args.branch,
                base_branch=args.base_branch,
                github_token=args.github_token,
                id_token=args.id_token,
            )
        )
    except KeyboardInterrupt:
        print("\n[Client] Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"[Client Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
