import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, AsyncIterator, Dict, List, Optional
import urllib.error
import urllib.request
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

load_dotenv()

from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.workflow import Workflow, START
from google.genai import types

try:
    from .subagents.clean_code import create_clean_code_agent
    from .subagents.maintainability import create_maintainability_agent
    from .subagents.defect_inspector import create_defect_inspector_agent
    from .subagents.synthesizer import create_synthesizer_agent
except (ImportError, ValueError):
    from subagents.clean_code import create_clean_code_agent
    from subagents.maintainability import create_maintainability_agent
    from subagents.defect_inspector import create_defect_inspector_agent
    from subagents.synthesizer import create_synthesizer_agent


EXCLUDED_PATTERNS = [
    r"package-lock\.json$",
    r"uv\.lock$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"\.min\.(js|css)$",
    r"dist/.*",
    r"build/.*",
    r"\.next/.*",
    r"node_modules/.*",
    r"\.venv/.*",
    r"__pycache__/.*",
    r"\.git/.*",
    r"\.scratch/.*",
    r"tsconfig\.tsbuildinfo$",
]


def _is_excluded(path: str) -> bool:
    for pat in EXCLUDED_PATTERNS:
        if re.search(pat, path):
            return True
    return False


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
        if "parts" in node_input:
            return "\n".join([str(p.get("text", "")) for p in node_input["parts"] if isinstance(p, dict) and p.get("text")])
    return str(node_input)


def _parse_request_payload(node_input: Any) -> Dict[str, Any]:
    """Parses JSON TaskRequest payload or falls back to plain dict."""
    if isinstance(node_input, dict):
        return node_input
    raw = _extract_text(node_input).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"pr_number": raw}


def _extract_owner_repo(repo_url: str) -> tuple[Optional[str], Optional[str]]:
    """Extracts owner and repo name from GitHub URL."""
    if not repo_url:
        return None, None
    clean = repo_url.rstrip("/").rstrip(".git")
    if "github.com/" in clean:
        parts = clean.split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None, None


async def fetch_pr_node(ctx: Context, node_input: Any) -> AsyncIterator[Event]:
    """Clones or checks out PR branch and extracts file diffs."""
    payload = _parse_request_payload(node_input)
    repo_url = payload.get("repo_url", "")
    pr_number = payload.get("pr_number")
    branch = payload.get("branch")
    base_branch = payload.get("base_branch", "main")
    github_token = payload.get("github_token")

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"[Workspace] 📦 Preparing workspace for Pull Request #{pr_number or 'current'}...")]
        )
    )

    workspace_dir = None
    head_sha = ""
    pr_title = ""
    pr_body = ""

    if repo_url and github_token:
        workspace_dir = Path(tempfile.mkdtemp(prefix="reviewer_ws_"))
        auth_url = repo_url
        if repo_url.startswith("https://"):
            auth_url = f"https://x-access-token:{github_token}@{repo_url[8:]}"

        # Shallow clone default branch first
        print(f"[Workflow: fetch_pr] Cloning {repo_url} into {workspace_dir}")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "50", auth_url, str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await proc.communicate()

        # Fetch PR branch
        if pr_number:
            fetch_proc = await asyncio.create_subprocess_exec(
                "git", "fetch", "origin", f"pull/{pr_number}/head:pr-{pr_number}",
                cwd=str(workspace_dir),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await fetch_proc.communicate()

            checkout_proc = await asyncio.create_subprocess_exec(
                "git", "checkout", f"pr-{pr_number}",
                cwd=str(workspace_dir),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await checkout_proc.communicate()

        # Ensure base branch is fetched
        await (await asyncio.create_subprocess_exec(
            "git", "fetch", "origin", base_branch,
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )).communicate()

        # Fetch latest commit SHA
        sha_proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        sha_out, _ = await sha_proc.communicate()
        head_sha = sha_out.decode().strip()

        # Try to get PR metadata from GitHub API if available
        owner, repo = _extract_owner_repo(repo_url)
        if owner and repo and pr_number:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "SDLC-Reviewer-Agent"
            }
            try:
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pr_data = json.loads(resp.read().decode())
                    pr_title = pr_data.get("title", "")
                    pr_body = pr_data.get("body", "")
            except Exception as e:
                print(f"[Workflow: fetch_pr] GitHub API fetch error: {e}")
    else:
        # Local execution mode
        workspace_dir = repo_root
        sha_proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        sha_out, _ = await sha_proc.communicate()
        head_sha = sha_out.decode().strip()

    # Get list of changed files
    diff_name_proc = await asyncio.create_subprocess_exec(
        "git", "diff", "--name-only", f"origin/{base_branch}...HEAD",
        cwd=str(workspace_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    diff_name_out, _ = await diff_name_proc.communicate()
    raw_files = [f.strip() for f in diff_name_out.decode().splitlines() if f.strip()]

    # Fallback to local base_branch...HEAD if origin/{base_branch} fails
    if not raw_files:
        diff_name_proc2 = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", f"{base_branch}...HEAD",
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        diff_name_out2, _ = await diff_name_proc2.communicate()
        raw_files = [f.strip() for f in diff_name_out2.decode().splitlines() if f.strip()]

    # Filter out lock files and binary/build artifacts
    filtered_files = [f for f in raw_files if not _is_excluded(f)]

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(
                text=f"[Diff] 🔍 Discovered {len(filtered_files)} changed files to review (excluded {len(raw_files) - len(filtered_files)} generated/lock files): {', '.join(filtered_files[:5])}{'...' if len(filtered_files) > 5 else ''}"
            )]
        )
    )

    # Get git diff content for filtered files
    file_diffs = {}
    file_contents = {}
    total_added = 0
    total_removed = 0

    for file_path in filtered_files:
        # Get diff for file
        diff_proc = await asyncio.create_subprocess_exec(
            "git", "diff", f"origin/{base_branch}...HEAD", "--", file_path,
            cwd=str(workspace_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        diff_out, _ = await diff_proc.communicate()
        diff_text = diff_out.decode("utf-8", errors="replace")
        if not diff_text:
            # Fallback
            diff_proc2 = await asyncio.create_subprocess_exec(
                "git", "diff", f"{base_branch}...HEAD", "--", file_path,
                cwd=str(workspace_dir),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            diff_out2, _ = await diff_proc2.communicate()
            diff_text = diff_out2.decode("utf-8", errors="replace")

        file_diffs[file_path] = diff_text

        # Count +/-
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                total_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_removed += 1

        # Read current file content if exists
        full_file_path = workspace_dir / file_path
        if full_file_path.is_file():
            try:
                # Read first 40KB
                content = full_file_path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 40000:
                    content = content[:40000] + "\n\n...[Truncated for Review]..."
                file_contents[file_path] = content
            except Exception as e:
                print(f"[Workflow: fetch_pr] Error reading {file_path}: {e}")

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(
                text=f"[Diff Summary] 📊 Total Diff Size: +{total_added} / -{total_removed} across {len(filtered_files)} authored files."
            )]
        )
    )

    output_data = {
        "workspace_dir": str(workspace_dir),
        "repo_url": repo_url,
        "pr_number": pr_number,
        "branch": branch,
        "base_branch": base_branch,
        "github_token": github_token,
        "head_sha": head_sha,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "filtered_files": filtered_files,
        "file_diffs": file_diffs,
        "file_contents": file_contents,
        "total_added": total_added,
        "total_removed": total_removed,
    }

    ctx.state["pr_data"] = output_data
    yield Event(output=output_data)


async def council_analysis_node(ctx: Context, node_input: Any) -> AsyncIterator[Event]:
    """Runs the three specialized Reviewer Council agents."""
    pr_data = ctx.state.get("pr_data") or node_input
    filtered_files = pr_data.get("filtered_files", [])
    file_diffs = pr_data.get("file_diffs", {})
    file_contents = pr_data.get("file_contents", {})

    if not filtered_files:
        yield Event(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="[Council] ℹ️ No authored code changes detected to review.")]
            )
        )
        ctx.state["council_results"] = {
            "clean_code": "No code changes.",
            "maintainability": "No code changes.",
            "defect_inspector": "No code changes.",
        }
        yield Event(output=ctx.state["council_results"])
        return

    # Build context for council subagents
    diff_bundle_parts = []
    for fp in filtered_files:
        diff_bundle_parts.append(f"### File: `{fp}`\n\n```diff\n{file_diffs.get(fp, '')}\n```\n")
        if fp in file_contents:
            diff_bundle_parts.append(f"#### Current Full File Content (`{fp}`):\n```\n{file_contents[fp]}\n```\n")

    diff_context = "\n".join(diff_bundle_parts)

    # 1. Clean Code Subagent
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="[Council: Clean Code] 🧹 Reviewing naming, clarity, simplicity, dead code, and DRY...")]
        )
    )
    clean_code_prompt = f"Please evaluate the following PR code changes for Clean Code & Readability:\n\n{diff_context}"
    async with create_clean_code_agent() as clean_code_agent:
        clean_code_res = await clean_code_agent.chat(clean_code_prompt)
        clean_code_text = await clean_code_res.text() if hasattr(clean_code_res, "text") and callable(clean_code_res.text) else (clean_code_res.text if hasattr(clean_code_res, "text") else str(clean_code_res))

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"[Council: Clean Code] ✅ Completed evaluation:\n{clean_code_text[:300]}...")]
        )
    )

    # 2. Maintainability Subagent
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="[Council: Maintainability] 🏗️ Reviewing architecture, modularity, type safety, and testability...")]
        )
    )
    maintainability_prompt = f"Please evaluate the following PR code changes for Maintainability & Architecture:\n\n{diff_context}"
    async with create_maintainability_agent() as maintainability_agent:
        maintainability_res = await maintainability_agent.chat(maintainability_prompt)
        maintainability_text = await maintainability_res.text() if hasattr(maintainability_res, "text") and callable(maintainability_res.text) else (maintainability_res.text if hasattr(maintainability_res, "text") else str(maintainability_res))

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"[Council: Maintainability] ✅ Completed evaluation:\n{maintainability_text[:300]}...")]
        )
    )

    # 3. Defect & Edge-Case Inspector
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="[Council: Defect Inspector] 🐞 Inspecting for edge cases, null hazards, and error handling...")]
        )
    )
    defect_prompt = f"Please evaluate the following PR code changes for Defects, Edge Cases, and Runtime Safety:\n\n{diff_context}"
    async with create_defect_inspector_agent() as defect_agent:
        defect_res = await defect_agent.chat(defect_prompt)
        defect_text = await defect_res.text() if hasattr(defect_res, "text") and callable(defect_res.text) else (defect_res.text if hasattr(defect_res, "text") else str(defect_res))

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"[Council: Defect Inspector] ✅ Completed evaluation:\n{defect_text[:300]}...")]
        )
    )

    council_results = {
        "clean_code": clean_code_text,
        "maintainability": maintainability_text,
        "defect_inspector": defect_text,
    }

    ctx.state["council_results"] = council_results
    yield Event(output=council_results)


async def synthesis_node(ctx: Context, node_input: Any) -> AsyncIterator[Event]:
    """Synthesizes council reviews and formats the GitHub PR review payload."""
    pr_data = ctx.state.get("pr_data", {})
    council_results = ctx.state.get("council_results", {})

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="[Synthesizer] 📊 Consolidating council reviews into final scorecard and inline comments...")]
        )
    )

    synth_prompt = (
        f"Pull Request Title: {pr_data.get('pr_title', 'N/A')}\n"
        f"PR Number: #{pr_data.get('pr_number', 'N/A')}\n"
        f"Files Changed: {', '.join(pr_data.get('filtered_files', []))}\n\n"
        f"=== Clean Code Reviewer Findings ===\n{council_results.get('clean_code', '')}\n\n"
        f"=== Maintainability Reviewer Findings ===\n{council_results.get('maintainability', '')}\n\n"
        f"=== Defect Inspector Findings ===\n{council_results.get('defect_inspector', '')}\n\n"
        f"Synthesize the findings into a consolidated GitHub PR Review Report and inline comments."
    )

    async with create_synthesizer_agent() as synthesizer_agent:
        synth_res = await synthesizer_agent.chat(synth_prompt)
        synth_text = await synth_res.text() if hasattr(synth_res, "text") and callable(synth_res.text) else (synth_res.text if hasattr(synth_res, "text") else str(synth_res))

    # Parse JSON payload from synthesizer output
    parsed_payload = {}
    json_match = re.search(r"```(?:json_review_payload|json)?\s*(\{.*?\})\s*```", synth_text, re.DOTALL)
    if json_match:
        try:
            parsed_payload = json.loads(json_match.group(1), strict=False)
        except Exception as e:
            print(f"[Workflow: synthesis] JSON parse error: {e}")

    overall_score = parsed_payload.get("overall_score", 85)
    clean_code_score = parsed_payload.get("clean_code_score", 85)
    maintainability_score = parsed_payload.get("maintainability_score", 85)
    defect_safety_score = parsed_payload.get("defect_safety_score", 85)
    summary_markdown = parsed_payload.get("summary_markdown", synth_text)
    inline_comments = parsed_payload.get("inline_comments", [])
    verdict = parsed_payload.get("verdict", "COMMENT")

    synthesis_output = {
        "overall_score": overall_score,
        "clean_code_score": clean_code_score,
        "maintainability_score": maintainability_score,
        "defect_safety_score": defect_safety_score,
        "verdict": verdict,
        "summary_markdown": summary_markdown,
        "inline_comments": inline_comments,
        "raw_synthesis": synth_text,
    }

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(
                text=f"[Synthesizer] 🏆 Review Scorecard:\n"
                     f"  - Clean Code: {clean_code_score}/100\n"
                     f"  - Maintainability: {maintainability_score}/100\n"
                     f"  - Defect Safety: {defect_safety_score}/100\n"
                     f"  - Overall Score: {overall_score}/100\n"
                     f"  - Inline Suggestions: {len(inline_comments)}"
            )]
        )
    )

    ctx.state["synthesis"] = synthesis_output
    yield Event(output=synthesis_output)


async def publish_review_node(ctx: Context, node_input: Any) -> AsyncIterator[Event]:
    """Publishes the consolidated review and inline comments to GitHub."""
    pr_data = ctx.state.get("pr_data", {})
    synthesis = ctx.state.get("synthesis", {})

    repo_url = pr_data.get("repo_url", "")
    pr_number = pr_data.get("pr_number")
    github_token = pr_data.get("github_token")
    head_sha = pr_data.get("head_sha", "")

    summary_md = synthesis.get("summary_markdown", "")
    inline_comments = synthesis.get("inline_comments", [])
    overall_score = synthesis.get("overall_score", 85)

    published = False
    comments_posted_count = 0

    if repo_url and pr_number and github_token:
        owner, repo = _extract_owner_repo(repo_url)
        if owner and repo:
            yield Event(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=f"[Publisher] 🚀 Publishing review to GitHub PR #{pr_number} ({owner}/{repo})...")]
                )
            )

            # Format formatted comments for GitHub Review API
            review_comments = []
            for item in inline_comments:
                path = item.get("path")
                line = item.get("line")
                body = item.get("body", "")
                if path and line:
                    try:
                        line_num = int(line)
                        review_comments.append({
                            "path": path,
                            "line": line_num,
                            "side": "RIGHT",
                            "body": body,
                        })
                    except (ValueError, TypeError):
                        pass

            # Prepare API request
            api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
                "User-Agent": "SDLC-Reviewer-Agent"
            }

            review_payload = {
                "body": summary_md,
                "event": "COMMENT",
            }
            if head_sha:
                review_payload["commit_id"] = head_sha
            if review_comments:
                review_payload["comments"] = review_comments

            # Attempt submission
            try:
                data_bytes = json.dumps(review_payload).encode("utf-8")
                req = urllib.request.Request(api_url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        published = True
                        comments_posted_count = len(review_comments)
                        yield Event(
                            content=types.Content(
                                role="model",
                                parts=[types.Part.from_text(text=f"[Publisher] ✅ Successfully submitted review with {comments_posted_count} inline comment(s).")]
                            )
                        )
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                print(f"[Workflow: publish_review] Primary review post failed HTTP {e.code}: {err_body}")

                # If inline comments caused 422 line mismatch, fallback to top-level review comment with inline suggestions appended
                if review_comments:
                    yield Event(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text="[Publisher] ⚠️ Notice: Specific line ranges in diff varied; falling back to unified review comment...")]
                        )
                    )
                    augmented_summary = summary_md + "\n\n### 📝 Line-Specific Suggestions\n"
                    for c in review_comments:
                        augmented_summary += f"\n- **`{c['path']}:{c['line']}`**:\n{c['body']}\n"

                    fallback_payload = {
                        "body": augmented_summary,
                        "event": "COMMENT",
                    }
                    if head_sha:
                        fallback_payload["commit_id"] = head_sha

                    try:
                        fallback_bytes = json.dumps(fallback_payload).encode("utf-8")
                        req2 = urllib.request.Request(api_url, data=fallback_bytes, headers=headers, method="POST")
                        with urllib.request.urlopen(req2, timeout=15) as resp2:
                            if resp2.status in (200, 201):
                                published = True
                                comments_posted_count = len(review_comments)
                                yield Event(
                                    content=types.Content(
                                        role="model",
                                        parts=[types.Part.from_text(text="[Publisher] ✅ Successfully posted consolidated review comment to PR.")]
                                    )
                                )
                    except Exception as e2:
                        print(f"[Workflow: publish_review] Fallback review post error: {e2}")

    # Emit final Markdown Execution Summary
    summary_report = (
        f"\n### SDLC Execution Summary\n\n"
        f"| Metric | Result |\n"
        f"|---|---|\n"
        f"| **Pull Request** | `#{pr_number or 'Local'}` |\n"
        f"| **Clean Code & Readability** | `{synthesis.get('clean_code_score', 85)}/100` |\n"
        f"| **Maintainability & Architecture** | `{synthesis.get('maintainability_score', 85)}/100` |\n"
        f"| **Defect & Safety Score** | `{synthesis.get('defect_safety_score', 85)}/100` |\n"
        f"| **Overall Quality Score** | `{overall_score}/100` |\n"
        f"| **Inline Suggestions** | `{len(inline_comments)}` |\n"
        f"| **GitHub Status** | `{'Published' if published else 'Completed'}` |\n"
        f"| **Workflow Status** | `status: COMPLETED` |\n"
    )

    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=summary_report)]
        )
    )

    final_output = {
        "status": "completed",
        "overall_score": overall_score,
        "clean_code_score": synthesis.get("clean_code_score", 85),
        "maintainability_score": synthesis.get("maintainability_score", 85),
        "defect_safety_score": synthesis.get("defect_safety_score", 85),
        "summary": summary_md,
        "inline_comments": inline_comments,
        "published": published,
        "comments_posted": comments_posted_count,
    }

    yield Event(output=final_output)


# Construct the ADK Workflow
reviewer_workflow = Workflow(
    name="reviewer_workflow",
    description="Automated SDLC Pull Request Reviewer Workflow",
    edges=[
        (START, fetch_pr_node),
        (fetch_pr_node, council_analysis_node),
        (council_analysis_node, synthesis_node),
        (synthesis_node, publish_review_node),
    ],
)

__all__ = ["reviewer_workflow"]
