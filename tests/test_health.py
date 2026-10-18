"""Run with: python3 -m unittest discover -s tests -v."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ANALYZER = Path(__file__).resolve().parents[1] / "analyzer.sh"


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = {
            "PATH": os.defpath,
            "HOME": str(self.repo),
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test Author",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, *args],
            cwd=self.repo, env=self.env, check=True, capture_output=True, text=True,
        )

    def commit(self, subject):
        self.git("commit", "-q", "--allow-empty", "-m", subject)

    def health(self, json_mode=True):
        result = subprocess.run(
            ["bash", str(ANALYZER), "health"] + (["--json"] if json_mode else []),
            cwd=self.repo, env=self.env, check=True, capture_output=True, text=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout) if json_mode else result.stdout

    def test_empty_repository_has_numeric_zeroes(self):
        report = self.health()
        self.assertEqual(report["commits_24h"], 0)
        self.assertEqual(report["commits_per_hour"], 0)
        self.assertEqual(report["learning_commits"], 0)
        self.assertEqual(report["learning_percent"], 0)
        self.assertEqual(report["status"], "CRITICAL")

    def test_non_learning_commit_produces_valid_json(self):
        self.commit("Fix: synthetic example")
        report = self.health()
        self.assertEqual(report["learning_commits"], 0)
        self.assertEqual(report["commits_per_hour"], 0.04)

    def test_subunit_rate_is_valid_json(self):
        self.commit("Learning: synthetic example")
        report = self.health()
        self.assertEqual(report["commits_per_hour"], 0.04)
        self.assertEqual(report["learning_commits"], 1)
        self.assertEqual(report["learning_percent"], 100)

    def test_learning_percentage_is_truncated(self):
        for subject in ["Learning: example", "Fix: example", "Docs: example"]:
            self.commit(subject)
        report = self.health()
        self.assertEqual(report["learning_percent"], 33)
        self.assertEqual(report["commits_per_hour"], 0.12)

    def test_status_thresholds(self):
        for count in range(1, 73):
            self.commit("Learning: example")
            if count in (23, 24, 71, 72):
                report = self.health()
                expected = "CRITICAL" if count < 24 else "WARNING" if count < 72 else "HEALTHY"
                self.assertEqual(report["commits_24h"], count)
                self.assertEqual(report["status"], expected)

    def test_human_output_has_single_learning_count(self):
        self.commit("Fix: example")
        self.assertIn("Learning commits: 0 (0%)", self.health(json_mode=False))


if __name__ == "__main__":
    unittest.main()
