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

try:
    os.chdir(repo_root)
except Exception:
    pass

from google.antigravity.hooks import post_tool_call


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
    from .subagents.decomposer import create_decomposer_agent
    from .subagents.test_writer import create_test_writer_agent
    from .subagents.engineer import create_engineer_agent
    from .subagents.test_runner import create_test_runner_agent
except (ImportError, ValueError):
    from subagents.decomposer import create_decomposer_agent
    from subagents.test_writer import create_test_writer_agent
    from subagents.engineer import create_engineer_agent
    from subagents.test_runner import create_test_runner_agent


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
    """Extracts a SUMMARY line or concise concluding line from subagent output."""
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


def _extract_runner_telemetry(text: str) -> tuple[bool, str, str]:
    """Parses STATUS, TEST_SUMMARY, and DIAGNOSTICS from test-runner output."""
    passed = "STATUS: PASS" in text or "STATUS:PASS" in text.replace(" ", "")
    summary = ""
    diagnostics = ""
    in_diagnostics = False
    diag_lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TEST_SUMMARY:"):
            summary = stripped[13:].strip()
            in_diagnostics = False
        elif stripped.upper().startswith("DIAGNOSTICS:"):
            first_diag = stripped[12:].strip()
            if first_diag and first_diag.lower() != "none":
                diag_lines.append(first_diag)
            in_diagnostics = True
        elif in_diagnostics:
            if stripped.upper().startswith("STATUS:") or stripped.upper().startswith("COMMAND:") or stripped.upper().startswith("EXIT_CODE:"):
                in_diagnostics = False
            elif stripped:
                diag_lines.append(stripped)

    if diag_lines:
        diagnostics = " | ".join(diag_lines[:2])
        if len(diagnostics) > 160:
            diagnostics = diagnostics[:157] + "..."

    if not summary:
        summary = "All tests passed" if passed else "Tests failed"
    if not diagnostics and not passed:
        error_lines = [l.strip() for l in text.splitlines() if "failed" in l.lower() or "error" in l.lower()]
        diagnostics = error_lines[0] if error_lines else "Verification checks failed"

    return passed, summary, diagnostics


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

        input_path = (workspace_dir / clean_path_str).resolve()
    else:
        # Local execution mode
        workspace_dir = repo_root
        input_path = Path(clean_path_str).resolve()
        if not input_path.is_absolute() or not input_path.exists():
            input_path = (repo_root / clean_path_str).resolve()

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


def _extract_task_badge_info(file_path: Path) -> str:
    """Extracts task number, stem, title, and short problem description for streaming badges."""
    stem = file_path.stem
    num_match = re.match(r"^(\d+)", stem)
    task_num = num_match.group(1) if num_match else stem.split("-")[0]

    title = ""
    desc = ""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        content = ""

    if content:
        title_match = re.search(r"^\s*#\s*(?:Task\s*\[?\d+\]?:\s*)?([^\n]+)", content, re.MULTILINE | re.IGNORECASE)
        if title_match:
            raw_title = title_match.group(1).strip()
            title = re.sub(r"^\[?Task\s*\d+\]?:\s*", "", raw_title, flags=re.IGNORECASE).strip()

        prob_match = re.search(r"##\s*(?:\d+\.\s*)?Problem\s*(?:to\s*Solve)?\s*\n+([^#\n]+)", content, re.IGNORECASE)
        if prob_match:
            raw_desc = prob_match.group(1).strip()
            raw_desc = re.sub(r"^[-*]\s*", "", raw_desc).strip()
            sentences = re.split(r"(?<=[.!?])\s+", raw_desc)
            desc = sentences[0].strip() if sentences else raw_desc
            if len(desc) > 85:
                desc = desc[:82].rsplit(" ", 1)[0] + "..."

    if not title:
        clean_name = re.sub(r"^\d+[-_]?", "", stem).replace("-", " ").replace("_", " ").strip()
        title = clean_name.title() if clean_name else stem

    if desc:
        return f"[Decomposer] 📝 Created task {task_num}: {stem} ({title} - {desc})"
    else:
        return f"[Decomposer] 📝 Created task {task_num}: {stem} ({title})"


async def decomposer_node(ctx: Any, node_input: Dict[str, Any]) -> AsyncIterator[PipelineEvent]:
    """Runs the decomposer subagent to break the spec into discrete task files with real-time streaming."""
    spec_file = Path(node_input["spec_file"])
    spec_dir = Path(node_input["spec_dir"])
    feature_name = node_input["feature_name"]

    yield PipelineEvent(f"[Decomposer] 📋 Analyzing spec `{spec_file.name}` to generate task decomposition...")

    print(f"[Workflow: decomposer] Running decomposer agent on {spec_file}")
    tasks_dir = spec_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    spec_content = spec_file.read_text(encoding="utf-8")

    event_queue: asyncio.Queue[str] = asyncio.Queue()
    seen_tasks: set[str] = set()
    stop_watcher = asyncio.Event()

    # Pre-populate any existing task files so we only stream new ones
    for existing in tasks_dir.glob("*.md"):
        seen_tasks.add(existing.name)

    async def scan_and_queue_new_tasks():
        if tasks_dir.exists():
            for p in sorted(tasks_dir.glob("*.md")):
                if p.name not in seen_tasks and p.stat().st_size > 0:
                    seen_tasks.add(p.name)
                    # Brief pause to allow concurrent file write flush
                    await asyncio.sleep(0.05)
                    badge = _extract_task_badge_info(p)
                    await event_queue.put(badge)

    @post_tool_call
    async def on_tool_done(data: Any):
        await scan_and_queue_new_tasks()

    async def watcher_loop():
        while not stop_watcher.is_set():
            await scan_and_queue_new_tasks()
            try:
                await asyncio.wait_for(stop_watcher.wait(), timeout=0.15)
            except asyncio.TimeoutError:
                pass
        await scan_and_queue_new_tasks()

    watcher_task = asyncio.create_task(watcher_loop())

    prompt = (
        f"Analyze the specification at `{spec_file}`.\n\n"
        f"Specification Content:\n"
        f"```markdown\n{spec_content}\n```\n\n"
        f"Decompose this specification into multiple discrete, small, independent engineering tasks.\n"
        f"Write each task to a sequentially numbered file under `{tasks_dir}/001-<task-name>.md`.\n"
        f"Ensure each task defines Target Files, Interfaces, Acceptance Criteria, and a Verification Command.\n\n"
        f"Conclude your response with a summary line in this format:\n"
        f"SUMMARY: Created N tasks (001-<name>, 002-<name>, ...)"
    )

    async def run_chat():
        async with create_decomposer_agent(hooks=[on_tool_done]) as decomposer:
            resp = await decomposer.chat(prompt)
            return await resp.text()

    chat_task = asyncio.create_task(run_chat())

    while not chat_task.done() or not event_queue.empty():
        try:
            badge_text = await asyncio.wait_for(event_queue.get(), timeout=0.1)
            print(f"[Workflow: decomposer] {badge_text}")
            yield PipelineEvent(badge_text)
        except asyncio.TimeoutError:
            pass

    decomposer_output = await chat_task
    stop_watcher.set()
    await watcher_task

    while not event_queue.empty():
        badge_text = event_queue.get_nowait()
        print(f"[Workflow: decomposer] {badge_text}")
        yield PipelineEvent(badge_text)

    # Discover generated task files
    task_files = sorted([str(p) for p in tasks_dir.glob("*.md")])
    if not task_files:
        # Fallback: extract markdown files if the model emitted markdown code blocks with file paths or headings
        pattern = r"```(?:markdown)?\s*(?:# Task\s*\[?(\d+)\]?:\s*([^\n]+)[\s\S]*?)```"
        matches = re.finditer(pattern, decomposer_output, re.IGNORECASE)
        idx = 1
        for m in matches:
            content = m.group(0).strip("`").strip()
            task_name = re.sub(r"[^a-zA-Z0-9_-]", "-", m.group(2).strip().lower()).strip("-")
            filename = f"{idx:03d}-{task_name}.md"
            (tasks_dir / filename).write_text(content, encoding="utf-8")
            idx += 1
        task_files = sorted([str(p) for p in tasks_dir.glob("*.md")])

    # Emit badge for any task files that were not yet emitted (e.g. from fallback)
    for p_str in task_files:
        p = Path(p_str)
        if p.name not in seen_tasks:
            seen_tasks.add(p.name)
            badge = _extract_task_badge_info(p)
            print(f"[Workflow: decomposer] {badge}")
            yield PipelineEvent(badge)

    if not task_files:
        raise RuntimeError(f"Decomposer did not create any task files in {tasks_dir}")

    output_data = {
        **node_input,
        "tasks_dir": str(tasks_dir),
        "task_files": task_files,
        "decomposer_summary": decomposer_output,
    }
    task_names = [Path(p).stem for p in task_files]
    print(f"[Workflow: decomposer] Created {len(task_files)} task files: {task_files}")

    yield PipelineEvent(
        f"[Decomposer] 📋 Generated {len(task_files)} tasks: {', '.join(task_names)}",
        output=output_data,
        state={"tasks_info": output_data}
    )


async def task_orchestrator_node(ctx: Any, node_input: Dict[str, Any]) -> AsyncIterator[PipelineEvent]:
    """Orchestrates test-writer, engineer, and test-runner subagents through each task."""
    task_files = node_input.get("task_files", [])
    total_tasks = len(task_files)
    results = []
    has_blocker = False

    yield PipelineEvent(f"[Orchestrator] 🚀 Starting task execution pipeline ({total_tasks} tasks total)...")

    for idx, task_file in enumerate(task_files, 1):
        task_name = Path(task_file).stem
        print(f"\n[Workflow: task_orchestrator] Processing Task {idx}/{total_tasks}: {task_file}")
        task_content = Path(task_file).read_text(encoding="utf-8")

        yield PipelineEvent(f"\n[Task {idx}/{total_tasks}: {task_name}] 🚀 Starting execution")

        # Step A: Test-Writer Authors Tests
        yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🧪 Test-Writer authoring verification tests...")
        print(f"[Workflow: task_orchestrator] Invoking test-writer for {task_file}")
        async with create_test_writer_agent() as test_writer:
            tw_prompt = (
                f"You are the Test-Writer Agent. Read the task specification at `{task_file}`:\n\n"
                f"{task_content}\n\n"
                f"Author or update test files to verify all acceptance criteria. "
                f"Do not run tests. Only write/edit test files.\n\n"
                f"Conclude your response with a 1-2 line summary:\n"
                f"SUMMARY: Created/updated <test_files> covering <key criteria>"
            )
            tw_resp = await test_writer.chat(tw_prompt)
            tw_output = await tw_resp.text()

        tw_summary = _extract_summary(tw_output, "Prepared test suite for acceptance criteria")
        yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🧪 Test-Writer prepared tests: {tw_summary}")

        # Step B: Code/Test Loop (Max 3 turns)
        turn = 0
        task_passed = False
        last_diagnostics = ""

        while turn < 3 and not task_passed:
            turn += 1
            print(f"[Workflow: task_orchestrator] Code/Test Loop - Task {idx}, Turn {turn}/3")
            yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] ⚙️ Engineer implementing solution (Turn {turn}/3)...")

            # Engineer writes/fixes code
            async with create_engineer_agent() as engineer:
                if turn == 1:
                    eng_prompt = (
                        f"Implement the solution for task `{task_file}`:\n\n"
                        f"{task_content}\n\n"
                        f"Tests have been prepared. Author clean implementation code to satisfy the task. "
                        f"Do not run tests.\n\n"
                        f"Conclude your response with a 1-2 line summary:\n"
                        f"SUMMARY: Modified <files> to implement <key features>"
                    )
                else:
                    eng_prompt = (
                        f"The previous test run failed with diagnostics:\n\n"
                        f"{last_diagnostics}\n\n"
                        f"Analyze the failure, identify the root cause, and update the implementation code. "
                        f"Do not run tests.\n\n"
                        f"Conclude your response with a 1-2 line summary:\n"
                        f"SUMMARY: Resolved <issues> in <files>"
                    )
                eng_resp = await engineer.chat(eng_prompt)
                eng_output = await eng_resp.text()

            eng_summary = _extract_summary(eng_output, "Updated implementation files")
            yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] ⚙️ Engineer completed (Turn {turn}/3): {eng_summary}")
            yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🔬 Test-Runner executing verification tests (Turn {turn}/3)...")

            # Test-Runner executes verification
            async with create_test_runner_agent() as test_runner:
                tr_prompt = (
                    f"Run the verification command for task `{task_file}`.\n"
                    f"Inspect the task details and test files, execute the tests with `run_command`, "
                    f"and return the structured status report (STATUS: PASS | FAIL)."
                )
                tr_resp = await test_runner.chat(tr_prompt)
                tr_output = await tr_resp.text()

            print(f"[Workflow: task_orchestrator] Test-Runner output:\n{tr_output}")
            passed, test_summary, diag = _extract_runner_telemetry(tr_output)

            if passed:
                task_passed = True
                print(f"[Workflow: task_orchestrator] Task {idx} PASSED on turn {turn}")
                yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] ✅ Verification PASSED on Turn {turn}/3 ({test_summary})")
                break
            else:
                last_diagnostics = tr_output
                yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] ❌ Verification FAILED on Turn {turn}/3: {diag}")
                if turn < 3:
                    yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🔄 Engineer starting Turn {turn + 1}/3 to resolve failures...")

        results.append({
            "task_file": task_file,
            "passed": task_passed,
            "turns_used": turn,
            "diagnostics": last_diagnostics if not task_passed else None,
        })

        if not task_passed:
            has_blocker = True
            print(f"[Workflow: task_orchestrator] Task {idx} failed after 3 turns. Halting task loop.")
            yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🛑 Blocked after 3 turns. Halting remaining tasks.")
            break
        else:
            # Commit passing task changes to git
            workspace_dir = node_input.get("workspace_dir")
            feature_name = node_input.get("feature_name", "feature")
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
                        commit_msg = f"feat({feature_name}): complete task {idx} - {task_name}"
                        await (await asyncio.create_subprocess_exec("git", "commit", "-m", commit_msg, cwd=str(workspace_dir))).communicate()
                        yield PipelineEvent(f"[Git] 💾 Committed changes for task {idx} ({task_name})")
                except Exception as e:
                    print(f"[Workflow: task_orchestrator] Git commit warning: {e}")

            yield PipelineEvent(f"[Task {idx}/{total_tasks}: {task_name}] 🎉 Task COMPLETED successfully ({turn} turn{'s' if turn > 1 else ''}).")

    status = "completed" if not has_blocker else "blocked"
    output_data = {
        **node_input,
        "results": results,
        "status": status,
    }
    yield PipelineEvent(
        f"[Orchestrator] 🏁 Task orchestration finished with status: {status.upper()}",
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
    status = node_input.get("status")
    feature_name = node_input.get("feature_name", "feature")
    branch_name = node_input.get("branch_name", "feature")
    base_branch = node_input.get("base_branch", "main")
    workspace_dir = node_input.get("workspace_dir")
    repo_url = node_input.get("repo_url")
    github_token = node_input.get("github_token")
    create_pr = node_input.get("create_pr", True)
    results = node_input.get("results", [])

    summary_lines = [
        f"### SDLC Execution Summary for `{feature_name}`",
        f"- **Branch**: `{branch_name}`",
        f"- **Base Branch**: `{base_branch}`",
        f"- **Overall Status**: `{status.upper()}`",
        "",
        "| Task | Status | Verification Turns |",
        "|---|---|---|",
    ]
    for r in results:
        task_name = Path(r["task_file"]).stem
        status_icon = "✅ PASS" if r["passed"] else "❌ FAIL (3 turns exceeded)"
        summary_lines.append(f"| `{task_name}` | {status_icon} | {r['turns_used']} |")

    summary_text = "\n".join(summary_lines)

    if status == "completed":
        summary_text += f"\n\nAll tasks verified successfully for branch `{branch_name}`."

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
                        f"Automated implementation and verification completed successfully for branch `{branch_name}` against `{base_branch}`.\n\n"
                        f"### 📋 Task Breakdown & Verification Status\n"
                        f"{summary_text}\n\n"
                        f"---\n*Generated automatically by SDLC Implementer Agent (Antigravity SDK)*"
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

                        # Update existing PR title and body
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
                            # Fallback without label if label doesn't exist
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

                        # Add update comment on existing PR
                        comment_text = (
                            f"🔄 **Implementer Agent Update**: Re-verified and updated branch `{branch_name}` against `{base_branch}`.\n\n"
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
                        # Create new PR
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
                            # Fallback without label in case labels do not exist in the repository
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
        summary_text += "\n\n🛑 Blocker encountered during task execution. Pull Request not created."

    print(f"\n{summary_text}\n")
    yield PipelineEvent(
        summary_text,
        output={"summary": summary_text, "status": status}
    )


async def run_implementer_pipeline(payload: Any) -> AsyncIterator[PipelineEvent]:
    """Runs the complete end-to-end SDLC implementer pipeline with native event streaming."""
    # 1. Branch Init
    branch_output = None
    async for ev in branch_init_node(None, payload):
        yield ev
        if ev.output:
            branch_output = ev.output

    if not branch_output:
        raise RuntimeError("Branch initialization step failed to produce workspace context.")

    # 2. Decomposer
    decomposer_output = None
    async for ev in decomposer_node(None, branch_output):
        yield ev
        if ev.output:
            decomposer_output = ev.output

    if not decomposer_output:
        raise RuntimeError("Decomposition step failed to produce task definitions.")

    # 3. Task Orchestrator (Test-Writer -> Engineer -> Test-Runner loop)
    orchestrator_output = None
    async for ev in task_orchestrator_node(None, decomposer_output):
        yield ev
        if ev.output:
            orchestrator_output = ev.output

    if not orchestrator_output:
        raise RuntimeError("Task orchestration step failed to produce execution results.")

    # 4. Pull Request
    async for ev in pr_node(None, orchestrator_output):
        yield ev


# Aliases for backwards compatibility
implementer_workflow = run_implementer_pipeline
implementer_pipeline = run_implementer_pipeline

__all__ = [
    "PipelineEvent",
    "PipelinePart",
    "PipelineContent",
    "branch_init_node",
    "decomposer_node",
    "task_orchestrator_node",
    "pr_node",
    "run_implementer_pipeline",
    "implementer_workflow",
    "implementer_pipeline",
    "_extract_task_badge_info",
    "_extract_summary",
    "_extract_runner_telemetry",
    "_parse_request_payload",
    "_extract_repo_slug",
]
