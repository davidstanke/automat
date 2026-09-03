import asyncio
from pathlib import Path
import tempfile
import unittest.mock
import pytest
import sys

pkg_dir = Path(__file__).resolve().parent
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

from workflow import single_shot_implementer_node, PipelineEvent


@pytest.mark.asyncio
async def test_single_shot_implementer_node_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_dir = Path(tmpdir) / "spec_test"
        spec_dir.mkdir()
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("# Feature Spec\n\nBuild feature XYZ.\n")

        events = []
        node_input = {
            "spec_file": str(spec_file),
            "spec_dir": str(spec_dir),
            "feature_name": "spec_test",
            "workspace_dir": str(tmpdir),
        }

        class MockImplementer:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                class MockResp:
                    async def text(self):
                        return "SUMMARY: Implemented spec_test (Modified/Created: src/app.py)"

                return MockResp()

        output_data = None
        with unittest.mock.patch("workflow.create_implementer_agent", return_value=MockImplementer()):
            async for ev in single_shot_implementer_node(None, node_input):
                events.append(ev.text)
                if ev.output:
                    output_data = ev.output

        assert output_data is not None
        assert output_data["status"] == "completed"
        assert "src/app.py" in output_data["implementation_summary"]
        assert any("Starting single-shot implementation" in ev for ev in events)
        assert any("Implementation completed: Implemented spec_test" in ev for ev in events)


if __name__ == "__main__":
    asyncio.run(test_single_shot_implementer_node_execution())
    print("Single-shot implementer tests passed!")
