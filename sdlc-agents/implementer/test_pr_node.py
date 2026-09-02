import asyncio
import json
from pathlib import Path
import tempfile
import unittest.mock
import sys

pkg_dir = Path(__file__).resolve().parent
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

from workflow import pr_node, _extract_repo_slug, PipelineEvent


def test_extract_repo_slug():
    assert _extract_repo_slug("https://github.com/davidstanke/managed-agents-demo.git") == "davidstanke/managed-agents-demo"
    assert _extract_repo_slug("https://github.com/davidstanke/managed-agents-demo") == "davidstanke/managed-agents-demo"
    assert _extract_repo_slug("https://x-access-token:ghp_123@github.com/owner/my-repo.git") == "owner/my-repo"
    assert _extract_repo_slug("git@github.com:owner/my-repo.git") == "owner/my-repo"
    assert _extract_repo_slug("") is None
    assert _extract_repo_slug(None) is None


async def test_pr_node_create_new_pr():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir)
        node_input = {
            "status": "completed",
            "feature_name": "user-auth",
            "branch_name": "feature/user-auth-123",
            "base_branch": "main",
            "workspace_dir": str(workspace_dir),
            "repo_url": "https://github.com/davidstanke/managed-agents-demo.git",
            "github_token": "ghp_mocktoken",
            "create_pr": True,
            "results": [
                {"task_file": "tasks/001-setup.md", "passed": True, "turns_used": 1},
                {"task_file": "tasks/002-auth.md", "passed": True, "turns_used": 2},
            ],
        }

        commands_run = []

        async def mock_subprocess_exec(*args, **kwargs):
            cmd = list(args)
            commands_run.append(cmd)

            class MockProcess:
                def __init__(self, cmd):
                    self.cmd = cmd
                    self.returncode = 0

                async def communicate(self):
                    if "pr" in self.cmd and "view" in self.cmd:
                        self.returncode = 1
                        return b"", b"no pull requests found"
                    elif "pr" in self.cmd and "create" in self.cmd:
                        self.returncode = 0
                        return b"https://github.com/davidstanke/managed-agents-demo/pull/42\n", b""
                    elif "git" in self.cmd and "push" in self.cmd:
                        self.returncode = 0
                        return b"", b""
                    return b"", b""

            return MockProcess(cmd)

        with unittest.mock.patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            events = []
            async for ev in pr_node(None, node_input):
                events.append(ev.text)

        # Verify git push was invoked with -u origin feature/user-auth-123
        assert any(
            cmd[:5] == ["git", "push", "-u", "origin", "feature/user-auth-123"]
            for cmd in commands_run
        ), f"git push -u not found in commands: {commands_run}"

        # Verify gh pr create was invoked with correct arguments
        create_calls = [cmd for cmd in commands_run if "pr" in cmd and "create" in cmd]
        assert len(create_calls) > 0, f"gh pr create not found: {commands_run}"
        create_cmd = create_calls[0]
        assert "--base" in create_cmd and "main" in create_cmd
        assert "--head" in create_cmd and "feature/user-auth-123" in create_cmd
        assert "--title" in create_cmd and "feat(user-auth): implement user-auth" in create_cmd
        assert "-R" in create_cmd and "davidstanke/managed-agents-demo" in create_cmd

        # Verify events
        assert any("[PR] 🎉 Pull Request created: https://github.com/davidstanke/managed-agents-demo/pull/42" in ev for ev in events)
        assert any("https://github.com/davidstanke/managed-agents-demo/pull/42" in ev for ev in events)


async def test_pr_node_update_existing_pr():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir)
        node_input = {
            "status": "completed",
            "feature_name": "user-auth",
            "branch_name": "feature/user-auth-123",
            "base_branch": "main",
            "workspace_dir": str(workspace_dir),
            "repo_url": "https://github.com/davidstanke/managed-agents-demo.git",
            "github_token": "ghp_mocktoken",
            "create_pr": True,
            "results": [
                {"task_file": "tasks/001-setup.md", "passed": True, "turns_used": 1},
            ],
        }

        commands_run = []

        async def mock_subprocess_exec(*args, **kwargs):
            cmd = list(args)
            commands_run.append(cmd)

            class MockProcess:
                def __init__(self, cmd):
                    self.cmd = cmd
                    self.returncode = 0

                async def communicate(self):
                    if "pr" in self.cmd and "view" in self.cmd:
                        self.returncode = 0
                        return json.dumps({"number": 42, "url": "https://github.com/davidstanke/managed-agents-demo/pull/42"}).encode(), b""
                    elif "pr" in self.cmd and "edit" in self.cmd:
                        self.returncode = 0
                        return b"", b""
                    elif "pr" in self.cmd and "comment" in self.cmd:
                        self.returncode = 0
                        return b"", b""
                    elif "git" in self.cmd and "push" in self.cmd:
                        self.returncode = 0
                        return b"", b""
                    return b"", b""

            return MockProcess(cmd)

        with unittest.mock.patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            events = []
            async for ev in pr_node(None, node_input):
                events.append(ev.text)

        # Verify gh pr edit and gh pr comment were called
        assert any("edit" in cmd for cmd in commands_run), f"gh pr edit not found: {commands_run}"
        assert any("comment" in cmd for cmd in commands_run), f"gh pr comment not found: {commands_run}"

        # Verify events
        assert any("[PR] 🔄 Pull Request updated: https://github.com/davidstanke/managed-agents-demo/pull/42" in ev for ev in events)


async def test_pr_node_push_only_when_create_pr_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir)
        node_input = {
            "status": "completed",
            "feature_name": "user-auth",
            "branch_name": "feature/user-auth-123",
            "base_branch": "main",
            "workspace_dir": str(workspace_dir),
            "repo_url": "https://github.com/davidstanke/managed-agents-demo.git",
            "github_token": "ghp_mocktoken",
            "create_pr": False,
            "results": [
                {"task_file": "tasks/001-setup.md", "passed": True, "turns_used": 1},
            ],
        }

        commands_run = []

        async def mock_subprocess_exec(*args, **kwargs):
            cmd = list(args)
            commands_run.append(cmd)

            class MockProcess:
                def __init__(self, cmd):
                    self.cmd = cmd
                    self.returncode = 0

                async def communicate(self):
                    return b"", b""

            return MockProcess(cmd)

        with unittest.mock.patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
            events = []
            async for ev in pr_node(None, node_input):
                events.append(ev.text)

        # Verify git push was called
        assert any(
            cmd[:5] == ["git", "push", "-u", "origin", "feature/user-auth-123"]
            for cmd in commands_run
        ), f"git push -u not found in commands: {commands_run}"

        # Verify gh CLI was NOT called
        assert not any("gh" in cmd for cmd in commands_run), f"gh should not be called when create_pr=False: {commands_run}"

        # Verify events contain push notice
        assert any("Branch `feature/user-auth-123` successfully pushed to remote" in ev for ev in events)


if __name__ == "__main__":
    test_extract_repo_slug()
    asyncio.run(test_pr_node_create_new_pr())
    asyncio.run(test_pr_node_update_existing_pr())
    asyncio.run(test_pr_node_push_only_when_create_pr_false())
    print("All PR node unit tests passed successfully!")
