# -*- coding: utf-8 -*-
"""v7.28 发布日期一致性回归测试。"""
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("config", ROOT / "tools" / "config.py")
config = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = config
spec.loader.exec_module(config)


class TestV728ReleaseDate(unittest.TestCase):
    def test_release_date_matches_active_docs(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        import re as _re
        self.assertTrue(_re.fullmatch(r"\d{4}-\d{2}-\d{2}", config.RELEASE_DATE), config.RELEASE_DATE)
        self.assertIn(f"v{config.SKILL_VERSION}（{config.RELEASE_DATE}）", skill)
        self.assertIn(f"v{config.SKILL_VERSION}**（{config.RELEASE_DATE}）", readme)


if __name__ == "__main__":
    unittest.main()
