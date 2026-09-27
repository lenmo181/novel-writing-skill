# -*- coding: utf-8 -*-
"""v7.28 SkillHub 更新器回归测试。"""
import importlib.util
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
spec = importlib.util.spec_from_file_location("update_skill", TOOLS / "update_skill.py")
update = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = update
spec.loader.exec_module(update)


class TestSkillUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skill_update_v728_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_parse_version_normalizes_missing_patch(self):
        self.assertEqual(update.parse_version("v7.28"), (7, 28, 0))
        self.assertEqual(update.parse_version("web-novel-writing-7.27.0.zip"), (7, 27, 0))

    def test_extract_strips_single_root_folder(self):
        archive = self.tmp / "skill.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("网络小说创作技能/SKILL.md", "> **版本**：v7.28\n")
            zf.writestr("网络小说创作技能/tools/config.py", 'SKILL_VERSION = "7.28"\n')
        out = self.tmp / "stage"
        candidate = update.extract_zip(archive, out)
        self.assertEqual(candidate, out)
        self.assertTrue((out / "SKILL.md").exists())
        self.assertTrue((out / "tools" / "config.py").exists())

    def test_extract_rejects_path_traversal(self):
        archive = self.tmp / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../outside.txt", "blocked")
        with self.assertRaises(ValueError):
            update.extract_zip(archive, self.tmp / "stage")

    def test_backup_and_replace_keep_recovery_copy(self):
        destination = self.tmp / "installed"
        (destination / "tools").mkdir(parents=True)
        (destination / "SKILL.md").write_text("> **版本**：v7.27\n", encoding="utf-8")
        (destination / "tools" / "config.py").write_text('SKILL_VERSION = "7.27"\n', encoding="utf-8")

        candidate = self.tmp / "candidate"
        (candidate / "tools").mkdir(parents=True)
        (candidate / "SKILL.md").write_text("> **版本**：v7.28\n", encoding="utf-8")
        (candidate / "tools" / "config.py").write_text('SKILL_VERSION = "7.28"\n', encoding="utf-8")

        backup = update.replace_skill(candidate, destination, self.tmp / "backups")
        self.assertIsNotNone(backup)
        self.assertEqual(update.read_local_version(destination), (7, 28, 0))
        self.assertEqual(update.read_local_version(backup), (7, 27, 0))

    def test_default_endpoint_points_to_skillhub(self):
        self.assertIn("api.skillhub.cn/api/v1/download", update.SKILLHUB_DOWNLOAD_URL)


if __name__ == "__main__":
    unittest.main()
