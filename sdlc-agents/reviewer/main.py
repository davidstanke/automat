#!/usr/bin/env python3
"""CLI entrypoint for running the Unified Reviewer ADK Agent."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Ensure repository root and package directory in sys.path
pkg_dir = Path(__file__).resolve().parent
repo_root = pkg_dir.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

from workflow import run_reviewer_pipeline


def _get_git_remote_url(cwd: Path) -> str:
    """Attempts to read origin URL from git config."""
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip()
    except Exception:
        return ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the SDLC Pull Request Reviewer Agent directly in-process."
    )
    parser.add_argument(
        "--pr",
        dest="pr_number",
        default=os.environ.get("PR_NUMBER"),
        help="Target Pull Request Number (e.g. 42).",
    )
    parser.add_argument(
        "--repo-url",
        default=os.environ.get("REPO_URL"),
        help="Repository URL (e.g. https://github.com/owner/repo.git).",
    )
    parser.add_argument(
        "--base-branch",
        default=os.environ.get("BASE_BRANCH", "main"),
        help="Base branch to diff against (default: main).",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("BRANCH"),
        help="Head feature branch name.",
    )
    parser.add_argument(
        "--head-sha",
        default=os.environ.get("HEAD_SHA"),
        help="Target head commit SHA being reviewed.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=os.environ.get("GITHUB_WORKSPACE") or str(repo_root),
        help="Directory of the checked-out repository (default: current workspace).",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token for fetching PR details and posting review comments.",
    )
    return parser.parse_args()


async def run_workflow(
    pr_number: str | int | None,
    repo_url: str | None,
    base_branch: str = "main",
    branch: str | None = None,
    head_sha: str | None = None,
    workspace_dir: str | Path | None = None,
    github_token: str | None = None,
):
    ws_path = Path(workspace_dir or repo_root).resolve()
    if not repo_url:
        repo_url = _get_git_remote_url(ws_path)

    # Normalize pr_number
    pr_num_val = None
    if pr_number:
        try:
            pr_num_val = int(pr_number)
        except (ValueError, TypeError):
            pr_num_val = str(pr_number)

    print("==================================================")
    print(f" Starting Reviewer Pipeline")
    print(f" Workspace:    {ws_path}")
    print(f" PR Number:    #{pr_num_val or 'Local'}")
    print(f" Base Branch:  {base_branch}")
    if branch:
        print(f" Head Branch:  {branch}")
    if head_sha:
        print(f" Head SHA:     {head_sha}")
    if repo_url:
        print(f" Repo URL:     {repo_url}")
    print("==================================================")

    payload = {
        "pr_number": pr_num_val,
        "repo_url": repo_url,
        "base_branch": base_branch,
        "branch": branch,
        "head_sha": head_sha,
        "workspace_dir": str(ws_path),
        "github_token": github_token,
    }

    final_status = "completed"
    try:
        async for event in run_reviewer_pipeline(payload):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        print(part.text, flush=True)
            elif str(event):
                print(str(event), flush=True)

            if hasattr(event, "output") and isinstance(event.output, dict):
                if "status" in event.output:
                    final_status = event.output["status"]
    except Exception as e:
        print(f"\n❌ Reviewer pipeline encountered an unhandled exception: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n==================================================")
    print(f" Reviewer pipeline finished with status: {final_status.upper()}")
    print("==================================================")

    if final_status not in ("completed", "success"):
        sys.exit(1)


def main():
    args = parse_args()
    asyncio.run(
        run_workflow(
            pr_number=args.pr_number,
            repo_url=args.repo_url,
            base_branch=args.base_branch,
            branch=args.branch,
            head_sha=args.head_sha,
            workspace_dir=args.workspace_dir,
            github_token=args.github_token,
        )
    )


if __name__ == "__main__":
    main()
