# -*- coding: utf-8 -*-
"""v7.36 治理回归测试：30项核心校验注册表与运行时版本治理。"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

class TestCoreRuleMap(unittest.TestCase):
    def test_exactly_30_items(self):
        text = (ROOT / "references" / "核心校验映射.md").read_text(encoding="utf-8")
        rows = [x for x in text.splitlines() if x.startswith("|") and re.match(r"^\| \d+ \|", x)]
        self.assertEqual(len(rows), 30)
        nums = [int(x.split("|")[1].strip()) for x in rows]
        self.assertEqual(nums, list(range(1, 31)))
        for row in rows:
            cells = [x.strip() for x in row.split("|")[1:-1]]
            self.assertEqual(len(cells), 7)
            self.assertTrue(cells[3], row)
            self.assertTrue(cells[4], row)
            self.assertTrue(cells[5], row)

    def test_map_is_referenced_by_skill(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("核心校验映射.md", skill)

class TestLintGovernance(unittest.TestCase):
    def test_lint_contains_core_map_check(self):
        lint = (TOOLS / "lint_skill.py").read_text(encoding="utf-8")
        self.assertIn("核心校验映射.md", lint)
        self.assertIn("range(1, 31)", lint)

class TestRepairRunner(unittest.TestCase):
    def test_help_and_no_file_are_controlled(self):
        runner = TOOLS / "repair_runner.py"
        h = subprocess.run([sys.executable, str(runner), "--help"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(h.returncode, 0)
        with __import__("tempfile").TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, str(runner), tmp, "--list"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 2)

if __name__ == "__main__":
    unittest.main(verbosity=1)
