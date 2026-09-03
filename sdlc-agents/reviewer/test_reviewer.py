import os
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

# Ensure reviewer module is in path
reviewer_dir = Path(__file__).resolve().parent
if str(reviewer_dir) not in sys.path:
    sys.path.insert(0, str(reviewer_dir))

from subagents.clean_code import get_clean_code_config
from subagents.maintainability import get_maintainability_config
from subagents.defect_inspector import get_defect_inspector_config
from subagents.synthesizer import get_synthesizer_config
from main import parse_args
from workflow import _extract_owner_repo, _is_excluded, _parse_request_payload


class TestReviewerSubagentConfigs(unittest.TestCase):
    def test_default_model_and_location(self):
        env = {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GEMINI_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            if "GOOGLE_GENAI_MODEL" in os.environ:
                del os.environ["GOOGLE_GENAI_MODEL"]
            if "GOOGLE_GENAI_LOCATION" in os.environ:
                del os.environ["GOOGLE_GENAI_LOCATION"]

            for cfg_fn in [
                get_clean_code_config,
                get_maintainability_config,
                get_defect_inspector_config,
                get_synthesizer_config,
            ]:
                cfg = cfg_fn()
                self.assertEqual(cfg.model, "gemini-3.7-flash")
                self.assertEqual(cfg.location, "global")
                self.assertEqual(cfg.project, "test-project")
                self.assertTrue(cfg.vertex)

    def test_custom_model_and_location_override(self):
        env = {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_GENAI_MODEL": "gemini-custom-model",
            "GOOGLE_GENAI_LOCATION": "us-central1",
            "GEMINI_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            for cfg_fn in [
                get_clean_code_config,
                get_maintainability_config,
                get_defect_inspector_config,
                get_synthesizer_config,
            ]:
                cfg = cfg_fn()
                self.assertEqual(cfg.model, "gemini-custom-model")
                self.assertEqual(cfg.location, "us-central1")


class TestReviewerMainCLI(unittest.TestCase):
    def test_parse_args(self):
        test_args = [
            "main.py",
            "--pr", "42",
            "--base-branch", "feature-base",
            "--head-sha", "abcdef123456",
            "--workspace-dir", "/tmp/ws",
            "--github-token", "ghp_secret",
            "--repo-url", "https://github.com/org/repo.git",
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_args()
            self.assertEqual(args.pr_number, "42")
            self.assertEqual(args.base_branch, "feature-base")
            self.assertEqual(args.head_sha, "abcdef123456")
            self.assertEqual(args.workspace_dir, "/tmp/ws")
            self.assertEqual(args.github_token, "ghp_secret")
            self.assertEqual(args.repo_url, "https://github.com/org/repo.git")


class TestReviewerWorkflowHelpers(unittest.TestCase):
    def test_extract_owner_repo(self):
        owner, repo = _extract_owner_repo("https://github.com/my-org/my-repo.git")
        self.assertEqual(owner, "my-org")
        self.assertEqual(repo, "my-repo")

        owner, repo = _extract_owner_repo("git@github.com:my-org/my-repo.git")
        self.assertEqual(owner, "my-org")
        self.assertEqual(repo, "my-repo")

        owner, repo = _extract_owner_repo("invalid-url")
        self.assertIsNone(owner)
        self.assertIsNone(repo)

    def test_is_excluded(self):
        self.assertTrue(_is_excluded("package-lock.json"))
        self.assertTrue(_is_excluded("poetry.lock"))
        self.assertTrue(_is_excluded("dist/bundle.js"))
        self.assertTrue(_is_excluded("assets/logo.png"))
        self.assertFalse(_is_excluded("src/index.ts"))
        self.assertFalse(_is_excluded("main.py"))

    def test_parse_request_payload(self):
        payload = _parse_request_payload('{"pr_number": 10, "base_branch": "dev"}')
        self.assertEqual(payload["pr_number"], 10)
        self.assertEqual(payload["base_branch"], "dev")

        dict_payload = _parse_request_payload({"pr_number": 20})
        self.assertEqual(dict_payload["pr_number"], 20)


if __name__ == "__main__":
    unittest.main()
