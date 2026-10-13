# -*- coding: utf-8 -*-
"""v7.45 超长篇规模化回归测试：章节索引增量、上下文预算、测试分片、千章性能。

钉住四件事：
  1. 索引是缓存不是事实——丢了能重建，不重算未变更章节；
  2. 上下文包有总量闸门，且当前章有保底不会被挤没；
  3. 测试分片不重不漏、分法稳定；
  4. 千章规模下元数据扫描不再是「每次全量重读」。
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import config  # noqa: E402


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


chapter_index = load_mod("chapter_index")
context_pack = load_mod("context_pack")
run_tests = load_mod("run_tests")
doctor = load_mod("doctor")


def make_book(root: Path, count: int, body_repeat: int = 40) -> None:
    book = root / "书稿"
    book.mkdir(parents=True, exist_ok=True)
    (root / "mind").mkdir(exist_ok=True)
    for i in range(1, count + 1):
        (book / f"第{i:04d}章_章节{i}.md").write_text(
            f"第{i}章 章节{i}\n" + "林舟向前走了一段路，屋里没有任何声音。" * body_repeat,
            encoding="utf-8")


class TestChapterIndex(unittest.TestCase):
    def test_first_build_scans_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_book(Path(tmp), 5) or Path(tmp)
            stats = chapter_index.build(root)["stats"]
            self.assertEqual(stats["total"], 5)
            self.assertEqual(stats["scanned"], 5)
            self.assertEqual(stats["from_index"], 0)

    def test_second_build_serves_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 5)
            chapter_index.build(root)
            stats = chapter_index.build(root)["stats"]
            self.assertEqual(stats["from_index"], 5)
            self.assertEqual(stats["scanned"], 0)

    def test_changed_file_is_rescanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 5)
            chapter_index.build(root)
            target = root / "书稿" / "第0003章_章节3.md"
            target.write_text("第3章 改写\n" + "改了。" * 20, encoding="utf-8")
            os.utime(target, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
            stats = chapter_index.build(root)["stats"]
            self.assertEqual(stats["scanned"], 1)
            self.assertEqual(stats["from_index"], 4)

    def test_index_is_disposable_cache(self):
        """删掉索引后重建，结果必须一致（索引不是事实来源）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 4)
            first = {r["chapter"]: r["chars"] for r in chapter_index.build(root)["records"]}
            (root / chapter_index.INDEX_DIR / chapter_index.INDEX_NAME).unlink()
            second = {r["chapter"]: r["chars"] for r in chapter_index.build(root)["records"]}
            self.assertEqual(first, second)

    def test_removed_chapter_dropped_from_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 4)
            chapter_index.build(root)
            (root / "书稿" / "第0004章_章节4.md").unlink()
            result = chapter_index.build(root)
            self.assertEqual(result["stats"]["total"], 3)
            self.assertEqual(result["stats"]["removed_entries"], 1)

    def test_lookup_works_with_and_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 6)
            chapter_index.build(root)
            self.assertEqual(chapter_index.lookup(root, 4), "书稿/第0004章_章节4.md")
            self.assertIsNone(chapter_index.lookup(root, 99))
            # 无索引时回退全目录匹配
            (root / chapter_index.INDEX_DIR / chapter_index.INDEX_NAME).unlink()
            self.assertEqual(chapter_index.lookup(root, 4), "书稿/第0004章_章节4.md")


class TestContextBudget(unittest.TestCase):
    def _pack_root(self, tmp: Path) -> Path:
        root = Path(tmp)
        make_book(root, 5, body_repeat=200)
        (root / "mind" / "角色状态快照.md").write_text("## 林舟\n- 状态：正常\n", encoding="utf-8")
        for i in range(1, 6):
            (root / "mind" / "回顾").mkdir(parents=True, exist_ok=True)
            (root / "mind" / "回顾" / f"第{i:03d}章回顾.md").write_text(f"第{i}章回顾\n" + "回顾内容。" * 100, encoding="utf-8")
        chapter_index.build(root)
        return root

    def test_budget_block_reported_and_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pack_root(Path(tmp))
            pack = context_pack.build_pack(root, chapter=5, recent=3,
                                           max_chars=6000, max_total=8000)
            budget = pack["budget"]
            self.assertEqual(budget["max_total"], 8000)
            self.assertLessEqual(budget["used"], 8000, "总预算未生效")
            self.assertTrue(budget["within_budget"])
            self.assertIn("current-chapter", budget["limits"])

    def test_current_chapter_has_floor(self):
        """预算再紧，正在写的这一章也必须留下可读的一截。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pack_root(Path(tmp))
            pack = context_pack.build_pack(root, chapter=5, recent=3,
                                           max_chars=6000, max_total=3000)
            limits = pack["budget"]["limits"]
            floor = int(3000 * config.DEFAULT_CONTEXT_CURRENT_FLOOR_RATIO)
            self.assertGreaterEqual(limits["current-chapter"], min(12000, floor))
            current = [i for i in pack["files"] if i["role"] == "current-chapter"]
            self.assertTrue(current and len(current[0]["content"]) > 0)

    def test_no_total_limit_keeps_legacy_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._pack_root(Path(tmp))
            pack = context_pack.build_pack(root, chapter=5, recent=2,
                                           max_chars=6000, max_total=0)
            self.assertEqual(pack["budget"]["limits"], {})
            self.assertTrue(pack["budget"]["within_budget"])


class TestSharding(unittest.TestCase):
    def test_shards_are_disjoint_and_complete(self):
        files = run_tests.discover_test_files()
        self.assertTrue(files)
        picked = []
        for i in (1, 2, 3):
            picked += run_tests.shard_files(files, i, 3)
        self.assertEqual(sorted(picked), sorted(files))
        self.assertEqual(len(picked), len(files))

    def test_shard_assignment_is_stable(self):
        files = run_tests.discover_test_files()
        first = run_tests.shard_files(files, 1, 3)
        second = run_tests.shard_files(files, 1, 3)
        self.assertEqual(first, second)


class TestScalePerformance(unittest.TestCase):
    """千章规模：元数据扫描必须走增量，不能每次全量重读。"""

    def test_incremental_scan_much_cheaper_than_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 400, body_repeat=30)
            t0 = time.perf_counter()
            chapter_index.build(root, rebuild=True)
            full = time.perf_counter() - t0
            t1 = time.perf_counter()
            stats = chapter_index.build(root)["stats"]
            incremental = time.perf_counter() - t1
            self.assertEqual(stats["scanned"], 0, "未变更时应全部命中缓存")
            self.assertLess(incremental, full,
                            f"增量扫描 {incremental:.3f}s 未快于全量 {full:.3f}s")

    def test_many_chapter_pack_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_book(root, 300, body_repeat=120)
            (root / "mind" / "角色状态快照.md").write_text("## 林舟\n- 状态：正常\n", encoding="utf-8")
            chapter_index.build(root)
            t0 = time.perf_counter()
            pack = context_pack.build_pack(root, chapter=300, recent=3,
                                           max_chars=6000, max_total=24000)
            elapsed = time.perf_counter() - t0
            self.assertLessEqual(pack["budget"]["used"], 24000)
            self.assertLess(elapsed, 10.0, f"300 章项目出包耗时 {elapsed:.2f}s，疑似退化成全目录扫描")


class TestSmokeRegistry(unittest.TestCase):
    """冒烟清单完整性（v7.45）：新 CLI 工具不进 RUNTIME_TOOLS 必须显式失败。

    背景：手工清单连续三版漏登记（bump_version / review_skeleton / chapter_index、
    run_tests），冒烟数停在 33 造成「全过」假象。检查器本身也需要反例钉住。
    """

    def _make_tree(self, tmp, extra=(), drop=()):
        tools = Path(tmp) / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        names = set(doctor.RUNTIME_TOOLS) | set(doctor.NON_CLI_TOOLS)
        for name in names:
            (tools / name).write_text("# stub\n", encoding="utf-8")
        for name in extra:
            (tools / name).write_text("# stub\n", encoding="utf-8")
        for name in drop:
            (tools / name).unlink()
        return tools

    def test_aligned_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_tree(tmp)
            result = doctor.smoke_registry_report(Path(tmp))
            self.assertTrue(result["ok"], result["detail"])

    def test_unregistered_tool_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_tree(tmp, extra=("zz_new_tool.py",))
            result = doctor.smoke_registry_report(Path(tmp))
            self.assertFalse(result["ok"])
            self.assertIn("zz_new_tool.py", result["detail"])
            self.assertIn("RUNTIME_TOOLS", result["fix"])

    def test_missing_registered_tool_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = sorted(doctor.RUNTIME_TOOLS)[0]
            self._make_tree(tmp, drop=(victim,))
            result = doctor.smoke_registry_report(Path(tmp))
            self.assertFalse(result["ok"])
            self.assertIn(victim, result["detail"])

    def test_real_tree_is_aligned(self):
        result = doctor.smoke_registry_report(ROOT)
        self.assertTrue(result["ok"],
                        f"真实 tools/ 与 RUNTIME_TOOLS 未对齐：{result['detail']}；{result['fix']}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
