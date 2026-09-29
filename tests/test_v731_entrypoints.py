# -*- coding: utf-8 -*-
"""v7.31 新手入口与免依赖 AI 味初筛回归测试。"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_check_chapter():
    spec = importlib.util.spec_from_file_location("check_chapter_v731", TOOLS / "check_chapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestV731Entrypoints(unittest.TestCase):
    def test_ai_lite_score_is_zero_dependency_and_bounded(self):
        check = load_check_chapter()
        score, reasons, metrics = check.ai_lite_score("他说：“好。”\n他转身离开。", ["他说：“好。”", "他转身离开。"])
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 10)
        self.assertIsInstance(reasons, list)
        self.assertEqual(metrics["chars"], check.count_chars("他说：“好。”\n他转身离开。"))

    def test_ai_lite_cli_does_not_require_chapter_length(self):
        with tempfile.TemporaryDirectory(prefix="novel_v731_") as td:
            path = Path(td) / "片段.md"
            path.write_text("一段很短的片段。", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "check_chapter.py"), str(path), "--ai-lite"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AI味粗测", result.stdout)
        self.assertNotIn("字数不足", result.stdout)

    def test_active_docs_reference_new_tool_page(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("工具选择.md", skill)
        self.assertIn("工具选择.md", readme)
        self.assertIn("--ai-lite", skill + readme)

    def test_new_tool_page_is_in_install_and_release_manifests(self):
        doctor = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        release = (ROOT / "tools" / "release_check.py").read_text(encoding="utf-8")
        self.assertIn('"references/工具选择.md"', doctor)
        self.assertIn('"references/工具选择.md"', release)

    def test_doctor_prints_a_first_next_step(self):
        result = subprocess.run(
            [sys.executable, str(TOOLS / "doctor.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("下一步：普通写作", result.stdout)
        self.assertIn("references/工具选择.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
