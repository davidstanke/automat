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
    return parser.parse_args()


async def run_workflow(spec_path: str):
    resolved_path = Path(spec_path).resolve()
    if resolved_path.is_dir():
        spec_file = resolved_path / "spec.md"
        if not spec_file.exists():
            print(f"Error: No spec.md found in directory: {resolved_path}", file=sys.stderr)
            sys.exit(1)
        target_path = str(resolved_path)
    elif resolved_path.is_file():
        target_path = str(resolved_path.parent)
    else:
        print(f"Error: Path does not exist: {resolved_path}", file=sys.stderr)
        sys.exit(1)

    print("==================================================")
    print(f" Starting Implementer Pipeline for: {target_path}")
    print("==================================================")

    async for event in run_implementer_pipeline({"spec_path": target_path}):
        text = str(event)
        if text:
            print(text, flush=True)

    print("\n==================================================")
    print(" Pipeline execution completed.")
    print("==================================================")


def main():
    args = parse_args()
    asyncio.run(run_workflow(args.spec_path))


if __name__ == "__main__":
    main()
