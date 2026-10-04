# -*- coding: utf-8 -*-
"""v7.40 export_assistant_txt 回归测试：作家助手本地导入 txt 导出。"""
import importlib.util
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

export_tool = load_mod("export_assistant_txt")


def mk_project(tmp, chapters):
    """chapters: {相对书稿文件名: 正文}；返回项目根。"""
    root = Path(tmp) / "测试书"
    (root / "书稿").mkdir(parents=True)
    for name, body in chapters.items():
        (root / "书稿" / name).write_text(body, encoding="utf-8")
    return root


def run_export(root, **kwargs):
    buf = StringIO()
    with redirect_stdout(buf):
        code = export_tool.export(str(root), **kwargs)
    return code, buf.getvalue()


class TestParseRange(unittest.TestCase):
    def test_range_forms(self):
        self.assertEqual(export_tool.parse_range("3"), {3})
        self.assertEqual(export_tool.parse_range("1-3"), {1, 2, 3})
        self.assertEqual(export_tool.parse_range("1,3,5-6"), {1, 3, 5, 6})

    def test_range_invalid(self):
        for bad in ("5-2", "0", "abc", ""):
            with self.assertRaises(ValueError):
                export_tool.parse_range(bad)


class TestExport(unittest.TestCase):
    def test_basic_export_order_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {
                "第2章_乙.md": "第2章 乙\n\n正文二。",
                "第10章_丙.md": "第10章 丙\n\n正文三。",
                "第001章_甲.md": "第1章 甲\n\n正文一。",
            })
            code, out = run_export(root)
            self.assertEqual(code, 0, out)
            txt = root / "导出" / "测试书_作家助手.txt"
            self.assertTrue(txt.is_file())
            raw = txt.read_bytes()
            self.assertTrue(raw[:3] == b"\xef\xbb\xbf", "默认 utf-8-sig 应带 BOM")
            text = raw.decode("utf-8-sig")
            titles = [l for l in text.splitlines() if l.startswith("第") and "章" in l[:6]]
            self.assertEqual(titles, ["第1章 甲", "第2章 乙", "第10章 丙"], "应按章号排序而非文件名")
            self.assertIn("正文二。", text)

    def test_title_synthesized_from_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {"第007章_没有标题行.md": "直接开始正文。"})
            code, out = run_export(root)
            self.assertEqual(code, 0, out)
            text = (root / "导出" / "测试书_作家助手.txt").read_text(encoding="utf-8-sig")
            self.assertTrue(text.startswith("第7章 没有标题行"), text[:40])
            self.assertIn("直接开始正文。", text)

    def test_markdown_artifacts_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {
                "第001章_甲.md": "第1章 甲\n\n# 小节标题\n\n```text\n代码块\n```\n\n---\n\n正文保留。",
            })
            code, out = run_export(root)
            self.assertEqual(code, 0, out)
            text = (root / "导出" / "测试书_作家助手.txt").read_text(encoding="utf-8-sig")
            for bad in ("#", "```", "---", "代码块"):
                self.assertNotIn(bad, text)
            self.assertIn("正文保留。", text)

    def test_range_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {f"第00{i}章_甲.md": f"第{i}章 甲\n\n正文{i}。" for i in range(1, 6)})
            code, out = run_export(root, range_spec="1,3")
            self.assertEqual(code, 0, out)
            text = (root / "导出" / "测试书_作家助手.txt").read_text(encoding="utf-8-sig")
            self.assertIn("正文1。", text)
            self.assertNotIn("正文2。", text)
            self.assertIn("正文3。", text)
            self.assertNotIn("正文4。", text)
            self.assertIn("--range 未命中跳过 3 个文件", out)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {"第001章_甲.md": "第1章 甲\n\n正文。"})
            code, out = run_export(root, dry_run=True)
            self.assertEqual(code, 0, out)
            self.assertFalse((root / "导出").exists(), "dry-run 不得写文件")
            self.assertIn("dry-run", out)

    def test_gbk_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {"第001章_甲.md": "第1章 甲\n\n中文正文。"})
            code, out = run_export(root, encoding="gbk")
            self.assertEqual(code, 0, out)
            txt = root / "导出" / "测试书_作家助手.txt"
            raw = txt.read_bytes()
            self.assertTrue(raw[:3] != b"\xef\xbb\xbf", "gbk 不应带 BOM")
            self.assertIn("中文正文。", raw.decode("gbk"))

    def test_out_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {"第001章_甲.md": "第1章 甲\n\n正文。"})
            target = Path(tmp) / "外部" / "投稿.txt"
            code, out = run_export(root, out=str(target))
            self.assertEqual(code, 0, out)
            self.assertTrue(target.is_file())


class TestExportErrors(unittest.TestCase):
    def test_missing_manuscript_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_export(Path(tmp))
            self.assertEqual(code, 2)
            self.assertIn("书稿", out)

    def test_empty_manuscript_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {})
            code, out = run_export(root)
            self.assertEqual(code, 2)

    def test_range_misses_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mk_project(tmp, {"第001章_甲.md": "第1章 甲\n\n正文。"})
            code, out = run_export(root, range_spec="9-100")
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
