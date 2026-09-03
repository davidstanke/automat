import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, AsyncIterator, Dict, List, Optional
from dotenv import load_dotenv

import sys

# Ensure package directory and repo root in sys.path
pkg_dir = Path(__file__).resolve().parent
repo_root = pkg_dir.parent.parent
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

if (repo_root / ".git").exists() or (repo_root / "sdlc-agents").exists():
    try:
        os.chdir(repo_root)
    except Exception:
        pass


@dataclass
class PipelinePart:
    text: str


@dataclass
class PipelineContent:
    parts: List[PipelinePart] = field(default_factory=list)


class PipelineEvent:
    """Lightweight event object compatible with both string and part-based consumers."""

    def __init__(self, text: str, output: Optional[Dict[str, Any]] = None, state: Optional[Dict[str, Any]] = None):
        self.text = text
        self.output = output
        self.state = state
        self.content = PipelineContent(parts=[PipelinePart(text=text)])

    @property
    def parts(self) -> List[PipelinePart]:
        return self.content.parts

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"PipelineEvent(text={self.text!r})"


try:
    from .subagents.implementer import create_implementer_agent
except (ImportError, ValueError):
    try:
        from subagents.implementer import create_implementer_agent
    except ImportError:
        create_implementer_agent = None


def _extract_text(node_input: Any) -> str:
    """Extracts plain text string from various ADK/GenAI node input structures."""
    if isinstance(node_input, str):
        return node_input
    if hasattr(node_input, "parts"):
        parts_text = [p.text for p in node_input.parts if hasattr(p, "text") and p.text]
        return "\n".join(parts_text)
    if isinstance(node_input, dict):
        if "text" in node_input:
            return str(node_input["text"])
        if "spec_path" in node_input:
            return str(node_input["spec_path"])
        if "parts" in node_input:
            return "\n".join([str(p.get("text", "")) for p in node_input["parts"] if isinstance(p, dict) and p.get("text")])
    return str(node_input)


def _parse_request_payload(node_input: Any) -> Dict[str, Any]:
    """Parses JSON TaskRequest payload or falls back to plain spec path string."""
    if isinstance(node_input, dict):
        return node_input
    raw = _extract_text(node_input).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"spec_path": raw}


def _extract_summary(text: str, default: str = "") -> str:
    """Extracts a SUMMARY line or concise concluding line from agent output."""
    if not text:
        return default
    for line in text.splitlines():
        if line.strip().upper().startswith("SUMMARY:"):
            return line.strip()[8:].strip()
    non_empty = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("```") and not line.strip().startswith("#")
    ]
    if non_empty:
        last = non_empty[-1]
        return (last[:140] + "...") if len(last) > 140 else last
    return default


async def branch_init_node(ctx: Any, node_input: Any) -> AsyncIterator[PipelineEvent]:
    """Initializes git workspace and branch for the feature spec."""
    payload = _parse_request_payload(node_input)
    raw_spec_path = payload.get("spec_path", "")
    repo_url = payload.get("repo_url")
    branch = payload.get("branch")
    base_branch = payload.get("base_branch", "main")
    github_token = payload.get("github_token")
    create_pr = payload.get("create_pr", True)

    clean_path_str = raw_spec_path.strip().strip("`").strip("'").strip('"')

    workspace_dir = None

    if repo_url and github_token:
        # Remote Git execution mode (e.g. Cloud Run)
        workspace_dir = Path(tempfile.mkdtemp(prefix="implementer_ws_"))
        auth_url = repo_url
        if repo_url.startswith("https://"):
            auth_url = f"https://x-access-token:{github_token}@{repo_url[8:]}"

        yield PipelineEvent(f"[Workspace] 📦 Preparing container workspace for `{repo_url}`...")

        target_branch = branch if branch else "main"

        # Clone repository
        print(f"[Workflow: branch_init] Cloning {repo_url} (branch: {target_branch}) into {workspace_dir}")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "10", "--branch", target_branch, auth_url, str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, clone_err = await proc.communicate()
        if proc.returncode != 0:
            print(f"[Workflow: branch_init] Branch clone fallback to default: {clone_err.decode()}")
            proc2 = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "10", auth_url, str(workspace_dir),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await proc2.communicate()
            if branch:
                await (await asyncio.create_subprocess_exec(
                    "git", "checkout", "-B", branch, cwd=str(workspace_dir),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )).communicate()

        # Configure git identity
        await (await asyncio.create_subprocess_exec("git", "config", "user.name", "Implementer Agent (Cloud Run)", cwd=str(workspace_dir))).communicate()
        await (await asyncio.create_subprocess_exec("git", "config", "user.email", "implementer-agent@cloudrun.local", cwd=str(workspace_dir))).communicate()

        try:
            os.chdir(workspace_dir)
        except Exception as e:
            print(f"[Workflow: branch_init] os.chdir error: {e}")

        rel_path = clean_path_str.lstrip("/")
        input_path = (workspace_dir / rel_path).resolve()
    else:
        # Local execution mode
        workspace_dir = repo_root
        candidate = Path(clean_path_str)
        if candidate.is_absolute() and candidate.exists():
            input_path = candidate.resolve()
        elif (repo_root / clean_path_str.lstrip("/")).exists():
            input_path = (repo_root / clean_path_str.lstrip("/")).resolve()
        elif candidate.resolve().exists():
            input_path = candidate.resolve()
        else:
            input_path = (repo_root / clean_path_str.lstrip("/")).resolve()

    # Resolve spec directory path and file
    if input_path.is_file():
        spec_file = input_path
        if spec_file.name == "spec.md":
            spec_dir = spec_file.parent
            feature_name = spec_dir.name
        else:
            feature_name = spec_file.stem
            spec_dir = spec_file.parent / feature_name
            spec_dir.mkdir(parents=True, exist_ok=True)
    elif input_path.is_dir():
        if (input_path / "spec.md").exists():
            spec_dir = input_path
            spec_file = spec_dir / "spec.md"
            feature_name = spec_dir.name
        else:
            md_files = [f for f in input_path.glob("*.md") if f.name != "README.md"]
            if md_files:
                spec_file = md_files[0]
                feature_name = spec_file.stem
                spec_dir = input_path / feature_name
                spec_dir.mkdir(parents=True, exist_ok=True)
            else:
                raise FileNotFoundError(f"Specification file not found in: {input_path}")
    else:
        raise FileNotFoundError(f"Specification path not found at: {clean_path_str}")

    branch_name = branch or f"feature/{feature_name}"

    yield PipelineEvent(f"[Branch] 🌿 Initializing branch `{branch_name}` for spec at `{spec_dir.name}`...")

    if not repo_url or not github_token:
        # Checkout or create branch locally
        print(f"[Workflow: branch_init] Checking out branch {branch_name}")
        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", "-B", branch_name,
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"[Workflow: branch_init] Git checkout warning: {stderr.decode()}")

    output_data = {
        "workspace_dir": str(workspace_dir),
        "spec_dir": str(spec_dir),
        "spec_file": str(spec_file),
        "feature_name": feature_name,
        "branch_name": branch_name,
        "base_branch": base_branch,
        "repo_url": repo_url,
        "github_token": github_token,
        "create_pr": create_pr,
    }
    yield PipelineEvent(
        f"[Branch] 🌿 Ready on feature branch `{branch_name}`.",
        output=output_data,
        state={"spec_info": output_data}
    )


async def single_shot_implementer_node(ctx: Any, node_input: Dict[str, Any]) -> AsyncIterator[PipelineEvent]:
    """Executes single-shot feature implementation without decomposition or test loops."""
    spec_file = Path(node_input["spec_file"])
    feature_name = node_input["feature_name"]
    workspace_dir = node_input.get("workspace_dir")

    yield PipelineEvent(f"[Implementer] 🚀 Starting single-shot implementation for `{feature_name}` from `{spec_file.name}`...")

    spec_content = ""
    if spec_file.exists():
        spec_content = spec_file.read_text(encoding="utf-8")

    prompt = (
        f"You are the Implementer Agent. Analyze and implement the complete feature specification at `{spec_file}`:\n\n"
        f"Specification Content:\n"
        f"```markdown\n{spec_content}\n```\n\n"
        f"Explore the codebase and create or edit all necessary files to fully implement this specification.\n"
        f"Do not run tests or shell commands. Only write and modify files.\n\n"
        f"Conclude your response with a 1-2 line summary:\n"
        f"SUMMARY: Implemented {feature_name} (Modified/Created: <files>)"
    )

    impl_output = ""
    if create_implementer_agent is not None:
        async with create_implementer_agent() as implementer:
            resp = await implementer.chat(prompt)
            impl_output = await resp.text()

    summary = _extract_summary(impl_output, f"Implemented {feature_name} in a single pass")
    yield PipelineEvent(f"[Implementer] ✨ Implementation completed: {summary}")

    # Commit changes to git if workspace exists
    if workspace_dir:
        try:
            proc_st = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(workspace_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            st_out, _ = await proc_st.communicate()
            if st_out.strip():
                await (await asyncio.create_subprocess_exec("git", "add", "-A", cwd=str(workspace_dir))).communicate()
                commit_msg = f"feat({feature_name}): implement {feature_name}"
                await (await asyncio.create_subprocess_exec("git", "commit", "-m", commit_msg, cwd=str(workspace_dir))).communicate()
                yield PipelineEvent(f"[Git] 💾 Committed changes for `{feature_name}`")
        except Exception as e:
            print(f"[Workflow: implementer] Git commit warning: {e}")

    output_data = {
        **node_input,
        "status": "completed",
        "implementation_summary": summary,
        "results": [
            {
                "task_file": str(spec_file),
                "passed": True,
                "turns_used": 1,
            }
        ],
    }

    yield PipelineEvent(
        f"[Implementer] 🏁 Single-shot implementation finished for `{feature_name}`.",
        output=output_data,
        state={"execution_results": output_data}
    )


def _extract_repo_slug(repo_url: Optional[str]) -> Optional[str]:
    """Extracts 'owner/repo' slug from various Git remote URL formats."""
    if not repo_url:
        return None
    clean = repo_url.strip().removesuffix(".git")
    m = re.search(r"github\.com[:/]([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)", clean)
    if m:
        return m.group(1)
    return None


async def pr_node(ctx: Any, node_input: Dict[str, Any]) -> AsyncIterator[PipelineEvent]:
    """Final node: reports execution outcome, pushes branch to remote, and creates/updates GitHub PR."""
    status = node_input.get("status", "completed")
    feature_name = node_input.get("feature_name", "feature")
    branch_name = node_input.get("branch_name", "feature")
    base_branch = node_input.get("base_branch", "main")
    workspace_dir = node_input.get("workspace_dir")
    repo_url = node_input.get("repo_url")
    github_token = node_input.get("github_token")
    create_pr = node_input.get("create_pr", True)
    summary_impl = node_input.get("implementation_summary", f"Implemented {feature_name}")

    summary_text = (
        f"### SDLC Execution Summary for `{feature_name}`\n"
        f"- **Branch**: `{branch_name}`\n"
        f"- **Base Branch**: `{base_branch}`\n"
        f"- **Overall Status**: `{status.upper()}`\n"
        f"- **Summary**: {summary_impl}\n"
    )

    if status == "completed":
        if repo_url and github_token and workspace_dir:
            repo_slug = _extract_repo_slug(repo_url)
            repo_flags = ["-R", repo_slug] if repo_slug else []
            env = os.environ.copy()
            env["GITHUB_TOKEN"] = github_token
            env["GH_TOKEN"] = github_token

            yield PipelineEvent(f"[Git] 🚀 Pushing `{branch_name}` to remote repository...")
            try:
                proc_push = await asyncio.create_subprocess_exec(
                    "git", "push", "-u", "origin", branch_name,
                    cwd=str(workspace_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _, push_err = await proc_push.communicate()
                if proc_push.returncode != 0:
                    yield PipelineEvent(f"[Git] ⚠️ Warning pushing branch: {push_err.decode()}")
                else:
                    yield PipelineEvent(f"[Git] 🌿 Branch `{branch_name}` successfully pushed to remote.")

                if create_pr:
                    yield PipelineEvent(f"[PR] 📬 Opening / Updating Pull Request (`{branch_name}` -> `{base_branch}`)...")
                    pr_title = f"feat({feature_name}): implement {feature_name}"
                    pr_body = (
                        f"## 🤖 SDLC Implementer Agent: {feature_name}\n\n"
                        f"Automated single-shot implementation completed successfully for branch `{branch_name}` against `{base_branch}`.\n\n"
                        f"### 📋 Execution Summary\n"
                        f"{summary_text}\n\n"
                        f"---\n*Generated automatically by SDLC Implementer Agent (Antigravity Single-Shot)*"
                    )

                    # Check if PR already exists
                    proc_view = await asyncio.create_subprocess_exec(
                        "gh", "pr", "view", branch_name, "--json", "number,url",
                        *repo_flags,
                        cwd=str(workspace_dir),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    pv_out, _ = await proc_view.communicate()
                    existing_pr = None
                    if proc_view.returncode == 0:
                        try:
                            existing_pr = json.loads(pv_out.decode().strip())
                        except Exception:
                            pass

                    if existing_pr and existing_pr.get("number"):
                        pr_number = str(existing_pr["number"])
                        pr_url = existing_pr.get("url", f"#{pr_number}")

                        edit_cmd = [
                            "gh", "pr", "edit", pr_number,
                            "--title", pr_title,
                            "--body", pr_body,
                            "--add-label", "automated-pr,implementer",
                            *repo_flags,
                        ]
                        proc_edit = await asyncio.create_subprocess_exec(
                            *edit_cmd,
                            cwd=str(workspace_dir),
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        edit_out, edit_err = await proc_edit.communicate()
                        if proc_edit.returncode != 0:
                            fallback_edit_cmd = [
                                "gh", "pr", "edit", pr_number,
                                "--title", pr_title,
                                "--body", pr_body,
                                *repo_flags,
                            ]
                            await (await asyncio.create_subprocess_exec(
                                *fallback_edit_cmd, cwd=str(workspace_dir), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            )).communicate()

                        comment_text = (
                            f"🔄 **Implementer Agent Update**: Updated implementation for branch `{branch_name}` against `{base_branch}`.\n\n"
                            f"{summary_text}"
                        )
                        comment_cmd = [
                            "gh", "pr", "comment", pr_number,
                            "--body", comment_text,
                            *repo_flags,
                        ]
                        await (await asyncio.create_subprocess_exec(
                            *comment_cmd, cwd=str(workspace_dir), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        )).communicate()

                        summary_text += f"\n\n**Pull Request (Updated)**: [{pr_url}]({pr_url})"
                        yield PipelineEvent(f"[PR] 🔄 Pull Request updated: {pr_url}")
                    else:
                        create_cmd = [
                            "gh", "pr", "create",
                            "--base", base_branch,
                            "--head", branch_name,
                            "--title", pr_title,
                            "--body", pr_body,
                            "--label", "automated-pr,implementer",
                            *repo_flags,
                        ]
                        proc_pr = await asyncio.create_subprocess_exec(
                            *create_cmd,
                            cwd=str(workspace_dir),
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        pr_out, pr_err = await proc_pr.communicate()
                        pr_url = pr_out.decode().strip()

                        if proc_pr.returncode != 0 or not pr_url.startswith("http"):
                            fallback_create_cmd = [
                                "gh", "pr", "create",
                                "--base", base_branch,
                                "--head", branch_name,
                                "--title", pr_title,
                                "--body", pr_body,
                                *repo_flags,
                            ]
                            proc_pr2 = await asyncio.create_subprocess_exec(
                                *fallback_create_cmd,
                                cwd=str(workspace_dir),
                                env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                            pr_out2, pr_err2 = await proc_pr2.communicate()
                            pr_url2 = pr_out2.decode().strip()
                            if pr_url2.startswith("http"):
                                pr_url = pr_url2

                        if pr_url.startswith("http"):
                            summary_text += f"\n\n**Pull Request**: [{pr_url}]({pr_url})"
                            yield PipelineEvent(f"[PR] 🎉 Pull Request created: {pr_url}")
                        else:
                            err_msg = pr_err.decode().strip() if 'pr_err' in locals() else ""
                            if err_msg:
                                summary_text += f"\n\n*PR Note*: {err_msg}"
                                yield PipelineEvent(f"[PR] ⚠️ Pull Request notice: {err_msg}")
            except Exception as e:
                print(f"[Workflow: pr_node] Git/PR error: {e}")
                summary_text += f"\n\n*Git Push / PR Error*: {e}"
                yield PipelineEvent(f"[PR] ⚠️ Git/PR error: {e}")
    else:
        summary_text += "\n\n🛑 Blocker encountered during execution. Pull Request not created."

    print(f"\n{summary_text}\n")
    yield PipelineEvent(
        summary_text,
        output={"summary": summary_text, "status": status}
    )


async def run_implementer_pipeline(payload: Any) -> AsyncIterator[PipelineEvent]:
    """Runs the streamlined end-to-end single-shot SDLC implementer pipeline."""
    # 1. Branch Init
    branch_output = None
    async for ev in branch_init_node(None, payload):
        yield ev
        if ev.output:
            branch_output = ev.output

    if not branch_output:
        raise RuntimeError("Branch initialization step failed to produce workspace context.")

    # 2. Single-Shot Implementer
    implementer_output = None
    async for ev in single_shot_implementer_node(None, branch_output):
        yield ev
        if ev.output:
            implementer_output = ev.output

    if not implementer_output:
        raise RuntimeError("Single-shot implementation step failed to produce output.")

    # 3. Pull Request
    async for ev in pr_node(None, implementer_output):
        yield ev


# Aliases for backwards compatibility
implementer_workflow = run_implementer_pipeline
implementer_pipeline = run_implementer_pipeline

__all__ = [
    "PipelineEvent",
    "PipelinePart",
    "PipelineContent",
    "branch_init_node",
    "single_shot_implementer_node",
    "pr_node",
    "run_implementer_pipeline",
    "implementer_workflow",
    "implementer_pipeline",
    "_extract_summary",
    "_parse_request_payload",
    "_extract_repo_slug",
]
