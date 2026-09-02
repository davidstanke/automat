#!/usr/bin/env python3
"""Client CLI for invoking the Implementer Agent service via A2A."""

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
    is_implementer_active,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Invoke the Implementer Agent service (with auto-launch if inactive)."
    )
    parser.add_argument(
        "spec_path",
        help="Path to feature specification directory (e.g. specs/000-example) or spec.md file.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("IMPLEMENTER_AGENT_URL"),
        help="Direct URL to implementer service (e.g. http://127.0.0.1:8090 or Cloud Run URL).",
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
        help="GitHub token for remote git repository push and PR creation.",
    )
    parser.add_argument(
        "--repo-url",
        default=os.environ.get("REPO_URL"),
        help="Target Git repository clone URL (e.g. https://github.com/owner/repo.git).",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("BRANCH"),
        help="Target feature branch name.",
    )
    return parser.parse_args()


async def ensure_server_url(url_override: Optional[str], host: str, no_auto_start: bool) -> str:
    """Returns an active server URL, launching a local instance if necessary."""
    if url_override:
        clean_url = url_override.rstrip("/")
        # Verify endpoint responds
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

    # Check for active local server in 8090..8099
    active_port = await find_active_server(host=host)
    if active_port:
        server_url = f"http://{host}:{active_port}"
        print(f"[Client] Found active implementer agent on port {active_port}: {server_url}")
        return server_url

    if no_auto_start:
        raise RuntimeError("No active implementer agent found and --no-auto-start was specified.")

    # Find free port and launch server with auto-reload
    port = find_free_port(host=host)
    print(f"[Client] Implementer agent not active. Launching on port {port} with auto-reload...")

    implementer_dir = Path(__file__).resolve().parent
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "server:app",
        "--app-dir",
        str(implementer_dir),
        "--host",
        host,
        "--port",
        str(port),
        "--reload",
        "--reload-dir",
        str(implementer_dir),
    ]

    log_file = implementer_dir / "server.log"
    with open(log_file, "a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=out,
            stderr=out,
            start_new_session=True,
        )

    print(f"[Client] Spawned server process (PID: {proc.pid}). Waiting for health check on port {port}...")

    # Wait for server to become ready
    server_url = f"http://{host}:{port}"
    for _ in range(20):
        await asyncio.sleep(0.5)
        if await is_implementer_active(port, host=host):
            print(f"[Client] Implementer agent is ready at {server_url}")
            return server_url

    raise TimeoutError(f"Server on port {port} failed to become healthy within 10 seconds. Check {log_file}")


async def dispatch_task(
    server_url: str,
    spec_path: str,
    id_token: Optional[str] = None,
    github_token: Optional[str] = None,
    repo_url: Optional[str] = None,
    branch: Optional[str] = None,
):
    resolved = Path(spec_path).resolve()
    if resolved.is_file() and resolved.name == "spec.md":
        resolved_str = str(resolved.parent)
    elif resolved.exists():
        resolved_str = str(resolved)
    else:
        resolved_str = spec_path

    print(f"\n==================================================")
    print(f" Dispatching Task to Implementer Service")
    print(f" URL:    {server_url}")
    print(f" Spec:   {resolved_str}")
    if branch:
        print(f" Branch: {branch}")
    if repo_url:
        print(f" Repo:   {repo_url}")
    print(f"==================================================\n")

    endpoint = f"{server_url}/tasks"
    payload = {
        "spec_path": resolved_str,
        "repo_url": repo_url,
        "branch": branch,
        "github_token": github_token,
        "create_pr": bool(github_token),
    }
    headers = {"Accept": "text/event-stream"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    # Execute request with SSE streaming (no timeout for long-running workflows)
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                print(f"Error {resp.status_code}: {error_body.decode(errors='replace')}", file=sys.stderr)
                sys.exit(1)

            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    content = line[6:]
                    print(content, flush=True)
                elif line.startswith("data:"):
                    content = line[5:]
                    print(content, flush=True)
                elif line.strip() and not line.startswith(":"):
                    print(line, flush=True)


async def main_async():
    args = parse_args()
    server_url = await ensure_server_url(
        url_override=args.url,
        host=args.host,
        no_auto_start=args.no_auto_start,
    )
    await dispatch_task(
        server_url=server_url,
        spec_path=args.spec_path,
        id_token=args.id_token,
        github_token=args.github_token,
        repo_url=args.repo_url,
        branch=args.branch,
    )


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
