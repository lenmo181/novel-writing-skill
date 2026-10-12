# -*- coding: utf-8 -*-
"""v7.43 发布链工程化回归测试：日期真源一致性、一键改版工具、发布链门禁。

钉住三件事：
  1. 发布日期不再有「测试副本」，只有一处真源（config.py），四源必须互相印证；
  2. bump_version.py 的点位清单不会静默漏改或误改；
  3. release_check 的 tag / 同号包两道门禁按预期判定。
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_meta import assert_release_consistent  # noqa: E402
from config import SKILL_VERSION, RELEASE_DATE  # noqa: E402


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bump_version = load_mod("bump_version")
release_check = load_mod("release_check")


class _Probe(unittest.TestCase):
    """空壳用例，用来复用 assertEqual/assertIn 的失败语义做反例断言。"""

    __test__ = False  # 不作为用例收集

    def runTest(self):
        pass


class TestReleaseMeta(unittest.TestCase):
    def test_current_repo_is_consistent(self):
        assert_release_consistent(self, ROOT, SKILL_VERSION, RELEASE_DATE)

    def test_rejects_stale_date(self):
        # 这正是 v7.42 的失效形态：真源已改，副本没跟上
        with self.assertRaises(AssertionError):
            assert_release_consistent(_Probe(), ROOT, SKILL_VERSION, "2020-01-01")

    def test_rejects_unknown_version(self):
        with self.assertRaises(AssertionError):
            assert_release_consistent(_Probe(), ROOT, "9.99", RELEASE_DATE)

    def test_rejects_bad_format(self):
        with self.assertRaises(AssertionError):
            assert_release_consistent(_Probe(), ROOT, SKILL_VERSION, "2026/10/12")

    def test_no_hardcoded_date_left_in_tests(self):
        # 拼接构造模式串，避免本文件自身命中
        pattern = "assertEqual(" + 'RELEASE_DATE, "'
        self_file = Path(__file__).name
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            if path.name == self_file:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(pattern, text,
                             f"{path.name} 仍硬编码发布日期断言（副本必然漂移）")


class TestBumpVersionRules(unittest.TestCase):
    def test_rules_cover_four_truth_sources(self):
        rules = bump_version.build_rules("7.42", "7.43", "2026-10-09", "2026-10-12",
                                         "发布链工程化版", "简介")
        files = {r["file"] for r in rules}
        for rel in ("tools/config.py", "SKILL.md", "README.md", "versions/CHANGELOG.md"):
            self.assertIn(rel, files, f"改版点位漏登记：{rel}")

    def test_every_rule_has_expect_or_is_whitelisted(self):
        rules = bump_version.build_rules("7.42", "7.43", "2026-10-09", "2026-10-12",
                                         "发布链工程化版", "简介")
        for rule in rules:
            self.assertIn(rule["type"], ("replace", "regex", "insert_before"))
            if rule["expect"] is None:
                # 只有版本台账的全量投影允许不校验命中次数
                self.assertEqual(rule["file"], "references/版本台账.md")

    def test_config_points_are_exact(self):
        rules = bump_version.build_rules("7.42", "7.43", "2026-10-09", "2026-10-12",
                                         "发布链工程化版", "简介")
        for rule in rules:
            if rule["file"] == "tools/config.py":
                self.assertEqual(rule["expect"], 1)


class TestBumpVersionApply(unittest.TestCase):
    def _apply(self, text, rules):
        return bump_version.apply_to_text(text, rules)

    def test_replace_hits_and_errors(self):
        rules = [{"type": "replace", "file": "x", "old": "v7.42", "new": "v7.43", "expect": 2}]
        text, hits, errors = self._apply("v7.42 / v7.42", rules)
        self.assertEqual(text, "v7.43 / v7.43")
        self.assertEqual(hits, ["×2"])
        self.assertEqual(errors, [])

    def test_missing_point_reports_error(self):
        rules = [{"type": "replace", "file": "x", "old": "不在文本里", "new": "y", "expect": 1}]
        _text, _hits, errors = self._apply("随便", rules)
        self.assertEqual(len(errors), 1)
        self.assertIn("未找到", errors[0])

    def test_count_mismatch_reports_error(self):
        rules = [{"type": "replace", "file": "x", "old": "v7.42", "new": "v7.43", "expect": 3}]
        _text, _hits, errors = self._apply("v7.42 / v7.42", rules)
        self.assertEqual(len(errors), 1)
        self.assertIn("期望 3 次", errors[0])

    def test_insert_before(self):
        rules = [{"type": "insert_before", "file": "x", "old": "锚点",
                  "new": "新条目\n", "expect": 1}]
        text, hits, errors = self._apply("前\n锚点\n后\n", rules)
        self.assertEqual(text, "前\n新条目\n锚点\n后\n")
        self.assertEqual(hits, ["insert ×1"])
        self.assertEqual(errors, [])

    def test_regex_rewrites_version_line(self):
        rules = [{"type": "regex", "file": "x",
                  "old": r"^> \*\*版本\*\*：v7\.42（2026-10-09）.+$",
                  "new": "> **版本**：v7.43（2026-10-12）· 新版", "expect": 1}]
        text, hits, errors = self._apply("> **版本**：v7.42（2026-10-09）· 旧版\n", rules)
        self.assertIn("v7.43（2026-10-12）· 新版", text)
        self.assertEqual(errors, [])


class TestReleaseChainGates(unittest.TestCase):
    def test_tag_check_skips_non_git_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = release_check.git_tag_check(Path(tmp))
        self.assertTrue(result["ok"])
        self.assertIn("非 git 工作区", result["detail"])

    def test_dist_check_requires_same_version_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            missing = release_check.dist_package_check(root, "7.43")
            self.assertFalse(missing["ok"])
            self.assertIn("没有 v7.43", missing["detail"])

            (root / "dist" / "网络小说创作技能_v7.43.0_skillhub.zip").write_text("x", encoding="utf-8")
            hit = release_check.dist_package_check(root, "7.43")
            self.assertTrue(hit["ok"])
            self.assertIn("v7.43.0_skillhub.zip", hit["detail"])

    def test_audit_reports_warnings_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = release_check.audit(Path(tmp))
        self.assertIn("warnings", report)
        # 非 git 的临时目录：tag 检查会作为警告条目出现
        self.assertTrue(any(w["name"] == "版本 tag" for w in report["warnings"]))
        self.assertFalse(report["ok"])  # dist 缺失 → 发布包同号判失败


if __name__ == "__main__":
    unittest.main(verbosity=1)
