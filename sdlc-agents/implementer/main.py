#!/usr/bin/env python3
"""CLI entrypoint for running the Unified Implementer ADK Workflow Agent."""

import argparse
import asyncio
from pathlib import Path
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Ensure repository root is in sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow import run_implementer_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the SDLC Implementer Agent on a feature specification."
    )
    parser.add_argument(
        "spec_path",
        help="Path to the specification directory (e.g., specs/000-example) or spec.md file.",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Target feature branch name.",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Target base branch (default: main).",
    )
    return parser.parse_args()


async def run_workflow(spec_path: str, branch: str | None = None, base_branch: str = "main"):
    path_obj = Path(spec_path)
    if path_obj.exists():
        resolved_path = path_obj.resolve()
    elif (repo_root / spec_path.lstrip("/")).exists():
        resolved_path = (repo_root / spec_path.lstrip("/")).resolve()
    else:
        resolved_path = path_obj.resolve()

    if resolved_path.is_file():
        target_path = str(resolved_path)
    elif resolved_path.is_dir():
        spec_file = resolved_path / "spec.md"
        if not spec_file.exists():
            md_files = [f for f in resolved_path.glob("*.md") if f.name != "README.md"]
            if not md_files:
                print(f"Error: No specification markdown file found in directory: {resolved_path}", file=sys.stderr)
                sys.exit(1)
        target_path = str(resolved_path)
    else:
        print(f"Error: Path does not exist: {spec_path} (resolved to {resolved_path})", file=sys.stderr)
        sys.exit(1)

    print("==================================================")
    print(f" Starting Implementer Pipeline for: {target_path}")
    if branch:
        print(f" Target Branch: {branch}")
    print("==================================================")

    payload = {
        "spec_path": target_path,
        "branch": branch,
        "base_branch": base_branch,
    }

    final_status = "completed"
    try:
        async for event in run_implementer_pipeline(payload):
            text = str(event)
            if text:
                print(text, flush=True)
            if hasattr(event, "output") and isinstance(event.output, dict):
                if "status" in event.output:
                    final_status = event.output["status"]
    except Exception as e:
        print(f"\n❌ Pipeline execution encountered an unhandled exception: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n==================================================")
    print(f" Pipeline execution finished with status: {final_status.upper()}")
    print("==================================================")

    if final_status == "blocked":
        print("❌ Execution was blocked due to task verification failure.", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()
    asyncio.run(run_workflow(args.spec_path, branch=args.branch, base_branch=args.base_branch))


if __name__ == "__main__":
    main()
