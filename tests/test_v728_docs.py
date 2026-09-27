# -*- coding: utf-8 -*-
"""v7.28 首次使用与故障恢复入口回归测试。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestV728Docs(unittest.TestCase):
    def test_quickstart_and_faq_are_referenced(self):
        quickstart = ROOT / "references" / "快速开始.md"
        faq = ROOT / "references" / "常见问题.md"
        self.assertTrue(quickstart.is_file())
        self.assertTrue(faq.is_file())

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for document in ("快速开始.md", "常见问题.md"):
            self.assertIn(document, skill)
            self.assertIn(document, readme)


if __name__ == "__main__":
    unittest.main()
