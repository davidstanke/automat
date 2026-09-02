import asyncio
from pathlib import Path
import tempfile
import unittest.mock
from workflow import decomposer_node, _extract_task_badge_info


async def test_decomposer_streaming():
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec_test"
        spec_dir.mkdir()
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("# Feature Spec\n\nSome spec content.\n")

        events = []
        node_input = {
            "spec_file": str(spec_file),
            "spec_dir": str(spec_dir),
            "feature_name": "spec_test",
        }

        class MockDecomposer:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                tasks_dir = spec_dir / "tasks"
                for i in range(1, 4):
                    await asyncio.sleep(0.05)
                    task_file = tasks_dir / f"00{i}-task-{i}.md"
                    task_file.write_text(
                        f"# Task [00{i}]: Subtask {i}\n\n## 1. Problem to Solve\nDescription for subtask {i}.\n"
                    )

                class MockResp:
                    async def text(self):
                        return "SUMMARY: Created 3 tasks"

                return MockResp()

        with unittest.mock.patch("workflow.create_decomposer_agent", return_value=MockDecomposer()):
            async for event in decomposer_node(None, node_input):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        events.append(part.text)

        assert any("Analyzing spec" in ev for ev in events), "Missing analyzing spec event"
        assert any("Created task 001: 001-task-1 (Subtask 1 - Description for subtask 1.)" in ev for ev in events)
        assert any("Created task 002: 002-task-2 (Subtask 2 - Description for subtask 2.)" in ev for ev in events)
        assert any("Created task 003: 003-task-3 (Subtask 3 - Description for subtask 3.)" in ev for ev in events)
        assert any("Generated 3 tasks: 001-task-1, 002-task-2, 003-task-3" in ev for ev in events)


async def test_decomposer_fallback_streaming():
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec_test"
        spec_dir.mkdir()
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("# Feature Spec\n")

        events = []
        node_input = {
            "spec_file": str(spec_file),
            "spec_dir": str(spec_dir),
            "feature_name": "spec_test",
        }

        mock_output = (
            "```markdown\n"
            "# Task [001]: Project Initialization\n\n"
            "## 1. Problem to Solve\n"
            "Setup the project base.\n"
            "```\n\n"
            "```markdown\n"
            "# Task [002]: State Management\n\n"
            "## 1. Problem to Solve\n"
            "Configure Zustand state store.\n"
            "```\n"
            "SUMMARY: Created 2 tasks"
        )

        class MockDecomposer:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                class MockResp:
                    async def text(self):
                        return mock_output

                return MockResp()

        with unittest.mock.patch("workflow.create_decomposer_agent", return_value=MockDecomposer()):
            async for event in decomposer_node(None, node_input):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        events.append(part.text)

        assert any("Created task 001: 001-project-initialization" in ev for ev in events)
        assert any("Created task 002: 002-state-management" in ev for ev in events)
        assert any("Generated 2 tasks: 001-project-initialization, 002-state-management" in ev for ev in events)


if __name__ == "__main__":
    asyncio.run(test_decomposer_streaming())
    asyncio.run(test_decomposer_fallback_streaming())
    print("All decomposer stream tests passed!")
