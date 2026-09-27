# -*- coding: utf-8 -*-
"""v7.26 发布级维护回归测试。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_tool(tool, *args):
    return subprocess.run(
        [sys.executable, "-B", str(TOOLS / tool), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
    )


class TestV726Maintenance(unittest.TestCase):
    def test_skill_lint_passes(self):
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("config_v730", ROOT / "tools" / "config.py")
        _cfg = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_cfg)
        result = run_tool("lint_skill.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"v{_cfg.SKILL_VERSION}", result.stdout)

    def test_check_chapter_help_uses_dialog_floor_15(self):
        result = run_tool("check_chapter.py", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("默认15", result.stdout)
        self.assertIn("默认 15/50", result.stdout)

    def test_zhuque_requires_external_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="novel_v726_") as td:
            path = Path(td) / "第001章_测试.md"
            path.write_text("第1章 测试\n\n" + "林舟把门推开，确认屋内没有人。" * 8, encoding="utf-8")
            result = run_tool("zhuque_check.py", str(path), "--key", "test-key")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("外部发送未获确认", result.stdout)


if __name__ == "__main__":
    unittest.main()
