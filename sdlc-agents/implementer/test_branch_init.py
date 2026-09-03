import asyncio
from pathlib import Path
import tempfile
import unittest.mock
import pytest

from workflow import branch_init_node, PipelineEvent


@pytest.mark.asyncio
async def test_branch_init_absolute_spec_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_file = Path(tmpdir) / "cater-agent-1788380697.md"
        spec_file.write_text("# Catering Agent Spec\n")

        payload = {
            "spec_path": str(spec_file),
            "branch": "cater-1128",
        }

        with unittest.mock.patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = unittest.mock.AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            events = []
            output_data = None
            async for ev in branch_init_node(None, payload):
                events.append(ev)
                if ev.output:
                    output_data = ev.output

            assert output_data is not None
            assert Path(output_data["spec_file"]).resolve() == spec_file.resolve()
            assert output_data["feature_name"] == "cater-agent-1788380697"
            assert output_data["branch_name"] == "cater-1128"
            assert Path(output_data["spec_dir"]).name == "cater-agent-1788380697"


@pytest.mark.asyncio
async def test_branch_init_directory_with_spec_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "001-example"
        spec_dir.mkdir()
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("# Spec Example\n")

        payload = {
            "spec_path": str(spec_dir),
            "branch": "feature/001-example",
        }

        with unittest.mock.patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = unittest.mock.AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            output_data = None
            async for ev in branch_init_node(None, payload):
                if ev.output:
                    output_data = ev.output

            assert output_data is not None
            assert Path(output_data["spec_file"]).resolve() == spec_file.resolve()
            assert Path(output_data["spec_dir"]).resolve() == spec_dir.resolve()
            assert output_data["feature_name"] == "001-example"


@pytest.mark.asyncio
async def test_branch_init_relative_spec_file():
    payload = {
        "spec_path": "docs/specs/_samples/cater-agent-1788380697.md",
        "branch": "cater-1128",
    }

    with unittest.mock.patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = unittest.mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        output_data = None
        async for ev in branch_init_node(None, payload):
            if ev.output:
                output_data = ev.output

        assert output_data is not None
        assert output_data["spec_file"].endswith("cater-agent-1788380697.md")
        assert output_data["feature_name"] == "cater-agent-1788380697"
        assert output_data["branch_name"] == "cater-1128"


@pytest.mark.asyncio
async def test_branch_init_leading_slash_spec_file():
    payload = {
        "spec_path": "/docs/specs/_samples/cater-agent-1788380697.md",
        "branch": "cater-1128",
    }

    with unittest.mock.patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = unittest.mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        output_data = None
        async for ev in branch_init_node(None, payload):
            if ev.output:
                output_data = ev.output

        assert output_data is not None
        assert output_data["spec_file"].endswith("cater-agent-1788380697.md")
        assert output_data["feature_name"] == "cater-agent-1788380697"


@pytest.mark.asyncio
async def test_branch_init_nonexistent_path_raises():
    payload = {
        "spec_path": "/nonexistent/path/to/spec.md",
    }
    with pytest.raises(FileNotFoundError):
        async for _ in branch_init_node(None, payload):
            pass


@pytest.mark.asyncio
async def test_main_run_workflow_preserves_spec_file():
    from main import run_workflow

    called_payload = None

    async def mock_pipeline(payload):
        nonlocal called_payload
        called_payload = payload
        yield PipelineEvent("done", output={"status": "completed"})

    with unittest.mock.patch("main.run_implementer_pipeline", side_effect=mock_pipeline):
        await run_workflow("docs/specs/_samples/cater-agent-1788380697.md", branch="cater-1128")

    assert called_payload is not None
    assert called_payload["spec_path"].endswith("cater-agent-1788380697.md")
    assert not called_payload["spec_path"].endswith("docs/specs")
    assert called_payload["branch"] == "cater-1128"
