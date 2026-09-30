# -*- coding: utf-8 -*-
"""v7.38 仓库许可证与配置回归测试。"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestReleaseConfig(unittest.TestCase):
    def test_apache_license(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Apache License"))
        self.assertIn("Version 2.0, January 2004", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)

    def test_repository_policy_files(self):
        for rel in (
            "NOTICE",
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".editorconfig",
            ".gitattributes",
            ".github/CODEOWNERS",
            ".github/dependabot.yml",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/workflows/verify.yml",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_current_version(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from config import SKILL_VERSION
        self.assertEqual(SKILL_VERSION, "7.38")

    def test_lint_and_evaluation_entrypoints(self):
        lint = subprocess.run(
            [sys.executable, str(ROOT / "tools/lint_skill.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(lint.returncode, 0, lint.stdout[-1500:] + lint.stderr[-1500:])

        eval_result = subprocess.run(
            [sys.executable, str(ROOT / "tools/eval_skill.py"), "--json"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(eval_result.returncode, 0, eval_result.stdout[-1000:] + eval_result.stderr[-1000:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
