# -*- coding: utf-8 -*-
"""v7.27 开源能力融合层回归测试。"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = load_mod("project_audit")
continuity = load_mod("continuity_check")
context = load_mod("context_pack")
diff = load_mod("chapter_diff")
snapshot = load_mod("snapshot_project")


def run_tool(tool, *args):
    return subprocess.run(
        [sys.executable, "-B", str(TOOLS / tool), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
    )


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="novel_v727_")
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)
        self.root = Path(self.td) / "书"
        for rel in ("书稿", "大纲", "设定", "mind", "mind/回顾", "剧本"):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        for rel in (
            "大纲/总纲.md", "大纲/卷纲.md", "大纲/章纲.md", "大纲/场景纲.md",
            "设定/世界观.md", "设定/角色.md", "mind/章节目录.md",
        ):
            (self.root / rel).write_text("# 档案\n", encoding="utf-8")

    def write_chapter(self, number, title="试探", body=None):
        body = body or "林舟推开门，听见远处传来脚步声。\n"
        path = self.root / "书稿" / f"第{number:03d}章_{title}.md"
        path.write_text(f"第{number}章 {title}\n\n{body}", encoding="utf-8")
        return path


class TestProjectAudit(ProjectCase):
    def test_clean_project_has_no_high_issue(self):
        self.write_chapter(1)
        self.write_chapter(2, "回声")
        (self.root / "mind/章节目录.md").write_text(
            "| 章号 | 标题 |\n|---|---|\n| 1 | 试探 |\n| 2 | 回声 |\n\n"
            "当前进度：已完成至第2章，下一章为第3章\n", encoding="utf-8")
        report = audit.audit(self.root)
        self.assertFalse(any(item["level"] == "high" for item in report["issues"]))

    def test_gap_returns_failure(self):
        self.write_chapter(1)
        self.write_chapter(3, "断层")
        result = run_tool("project_audit.py", str(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertIn("CHAPTER_GAP", result.stdout)


class TestContinuity(ProjectCase):
    def test_role_and_foreshadow_order_are_reported(self):
        self.write_chapter(1)
        (self.root / "mind/角色状态快照.md").write_text(
            "## 林舟\n- 首次出场章：第3章\n- 最后出场：第1章\n", encoding="utf-8")
        (self.root / "mind/伏笔追踪表.md").write_text(
            "| 编号 | 内容 | 埋设章 | 预计回收章 | Tier | 状态 |\n"
            "| F1 | 铜锁 | 第5章 | 第2章 | T3 | 未回收 |\n", encoding="utf-8")
        report = continuity.check(self.root)
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("ROLE_ORDER", codes)
        self.assertIn("FORESHADOW_ORDER", codes)


class TestContextPack(ProjectCase):
    def test_pack_contains_hash_and_recent_chapter(self):
        self.write_chapter(1, "起点")
        self.write_chapter(2, "试探")
        (self.root / "mind/角色状态快照.md").write_text("## 林舟\n- 状态：正常\n", encoding="utf-8")
        pack = context.build_pack(self.root, chapter=2, recent=1, max_chars=200)
        paths = {item["path"].replace("\\", "/") for item in pack["files"]}
        current = "书稿/第002章_试探.md"
        self.assertIn(current, paths)
        entry = next(item for item in pack["files"] if item["path"].replace("\\", "/") == current)
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertIn("mind/章节目录.md", paths)


class TestChapterDiff(ProjectCase):
    def test_large_delete_warning(self):
        before = Path(self.td) / "before.md"
        after = Path(self.td) / "after.md"
        before.write_text("第1章 试探\n\n" + "林舟继续向前走，屋里没有任何声音。" * 12, encoding="utf-8")
        after.write_text("第1章 试探\n\n" + "林舟停下脚步。", encoding="utf-8")
        report = diff.build_report(before, after)
        self.assertTrue(report["large_delete"])
        result = run_tool("chapter_diff.py", str(before), str(after), "--strict")
        self.assertEqual(result.returncode, 1)
        self.assertIn("删除比例超过", result.stdout)


class TestSnapshot(ProjectCase):
    def test_snapshot_writes_manifest_and_copies_canon(self):
        self.write_chapter(1)
        (self.root / "mind/作者记忆.md").write_text("- [推断偏好] 2026-09-22 | 少用套话\n", encoding="utf-8")
        target, manifest = snapshot.create_snapshot(self.root, "test", include_chapters=False)
        self.assertTrue((target / "manifest.json").is_file())
        self.assertGreaterEqual(len(manifest["files"]), 1)
        self.assertFalse((target / "书稿").exists())
        saved = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["label"], "test")


if __name__ == "__main__":
    unittest.main()
