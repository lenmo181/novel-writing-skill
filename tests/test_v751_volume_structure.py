"""v7.51 长篇分卷规则回归测试。"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def load_mod(name, source=None):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (source or f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen_index = load_mod("gen_index_v751", "gen_index.py")
init_project = load_mod("init_project_v751", "init_project.py")


class VolumeStructureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="novel_v751_volume_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_init_project_marks_volume_requirement(self):
        target = self.temp_dir / "新书"
        report = init_project.init_project(target, "卷章测试", "悬疑", "番茄", "80万字", dry_run=False)
        self.assertIn("大纲/卷纲.md", report["created"])
        metadata = json.loads((target / "项目元数据.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["volume_required"])
        toc = (target / "mind/章节目录.md").read_text(encoding="utf-8")
        self.assertIn("| 章号 | 卷号 | 标题 |", toc)
        self.assertIn("当前卷：第1卷", toc)

    def test_gen_index_infers_volume_from_volume_outline(self):
        root = self.temp_dir / "书"
        (root / "书稿").mkdir(parents=True)
        (root / "大纲").mkdir()
        (root / "mind").mkdir()
        (root / "大纲/卷纲.md").write_text(
            "| 卷号 | 卷名 | 起止章 |\n|---|---|---|\n| 1 | 起局 | 1-2 |\n| 2 | 入局 | 3-4 |\n",
            encoding="utf-8",
        )
        for number in range(1, 5):
            (root / "书稿" / f"第{number:03d}章_测试.md").write_text(
                f"第{number}章 测试\n\n主角推门看见门后的灯光。\n", encoding="utf-8"
            )
        self.assertEqual(gen_index.build(str(root)), 0)
        toc = (root / "mind/章节目录.md").read_text(encoding="utf-8")
        self.assertIn("| 1 | 1 | 测试 |", toc)
        self.assertIn("| 3 | 2 | 测试 |", toc)
        self.assertIn("当前卷：第2卷", toc)


if __name__ == "__main__":
    unittest.main()
