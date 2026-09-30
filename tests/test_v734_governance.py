# -*- coding: utf-8 -*-
"""v7.35 规则治理回归测试：以行为测试为主（config 传播/边界值/二审/题材反例），
替代 v733 的「源码含某数字」式文本断言。目标：减少误报，而不是堆测试数。"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

import config  # noqa: E402
full_review = importlib.import_module("full_review") if "full_review" in sys.modules else None
if full_review is None:
    spec = importlib.util.spec_from_file_location("full_review", TOOLS / "full_review.py")
    full_review = importlib.util.module_from_spec(spec)
    sys.modules["full_review"] = full_review
    spec.loader.exec_module(full_review)
check_chapter = importlib.import_module("check_chapter")


def make_chapter(path, title, paras):
    path.write_text(f"{title}\n" + "\n\n".join(paras), encoding="utf-8")


def chapter_paras(target_len, n_extra=30):
    """构造目标段长 + 常规短段的章节数组（其余段合规）。"""
    paras = ["“你确定？”“确定。”他说完便转身离开。"]
    paras += ["他沿石阶而上，脚步很稳。"] * n_extra
    paras += ["这" * target_len]
    paras += ["他没有再说话，只是继续往前走。"] * 10
    return paras


class TestWallBoundary(unittest.TestCase):
    """文字墙边界行为：139 通过 / 140 边界通过 / 141 硬卡（真源 config.WALL_HARD=140）。"""

    def _wall_flags(self, plen, wall=None):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "第001章_边界.md"
            make_chapter(f, "第1章 边界", chapter_paras(plen))
            args = [sys.executable, str(TOOLS / "check_chapter.py"), str(f)]
            if wall:
                args += ["--wall", str(wall)]
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
            hard = any(l.startswith("[✗]") and "文字墙" in l for l in r.stdout.splitlines())
            return hard, r.stdout

    def test_139_passes(self):
        hard, _ = self._wall_flags(139)
        self.assertFalse(hard, "139 字段落不应硬卡")

    def test_140_boundary_passes(self):
        hard, _ = self._wall_flags(140)
        self.assertFalse(hard, "140=边界值应通过（>140 才硬卡）")

    def test_141_hard_fails(self):
        hard, _ = self._wall_flags(141)
        self.assertTrue(hard, "141 字段落必须硬卡")

    def test_wall_override_200(self):
        hard, _ = self._wall_flags(190, wall=200)
        self.assertFalse(hard, "说书体 --wall 200 下 190 字段落合法（题材例外）")

    def test_config_propagation_wall(self):
        """改 config.WALL_HARD 后 check() 行为同步变化（延迟绑定）。"""
        old = config.WALL_HARD
        try:
            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / "第001章_传播.md"
                make_chapter(f, "第1章 传播", chapter_paras(145))
                config.WALL_HARD = 200
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = check_chapter.check(str(f), 100, 100000, quote_mode="any", dialog_min=0, dialog_max=100)
                out = buf.getvalue()
                # 145<200：无墙硬卡；但字数下限 100 会挡——用宽区间，只看墙
                self.assertNotIn("文字墙：", out)
        finally:
            config.WALL_HARD = old


class TestFullReviewThresholds(unittest.TestCase):
    """full_review 阈值来自 config 且运行时可覆盖（传播行为测试）。"""

    def _mk(self, tmp, chapters):
        root = Path(tmp)
        (root / "书稿").mkdir(parents=True)
        for num, body in chapters:
            (root / "书稿" / f"第{num:03d}章_章{num}.md").write_text(f"第{num}章 章{num}\n{body}", encoding="utf-8")
        return root

    def _queue(self, root):
        return json.loads((root / "mind" / "全文审稿队列.json").read_text(encoding="utf-8"))

    def test_dialog_threshold_propagation(self):
        """默认 55 下对话 60% 出 P2；把 config.FULL_REVIEW_DIALOG_MAX 提到 70 后不再出。"""
        talky = "“很好，就这样办，我们继续说下去。”" * 60 + "他沉默地把剩余的事做完，没有再多说一个字，转身离开院子。" * 30  # ≈60% 对话
        plain = "他沉默地做完了所有的事，没有说话。" * 60
        old = config.FULL_REVIEW_DIALOG_MAX
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = self._mk(tmp, [(1, plain), (2, talky)])
                full_review.run_review(root)
                q = self._queue(root)
                self.assertTrue(any("对话占比" in i["msg"] for i in q["issues"]), "默认阈值 55 应触发对话告警")
            with tempfile.TemporaryDirectory() as tmp:
                root = self._mk(tmp, [(1, plain), (2, talky)])
                config.FULL_REVIEW_DIALOG_MAX = 70
                full_review.run_review(root)
                q = self._queue(root)
                self.assertFalse(any("对话占比" in i["msg"] for i in q["issues"]), "阈值提到 70 后 60% 对话不应再告警")
        finally:
            config.FULL_REVIEW_DIALOG_MAX = old

    def test_queue_ten_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, [(1, "甲" * 1900), (3, "乙" * 1900)])  # 断档
            full_review.run_review(root)
            q = self._queue(root)
            self.assertGreaterEqual(len(q["issues"]), 1)
            for field in ("issue_id", "level", "cat", "loc", "msg", "evidence",
                          "recommended_action", "repair_scope", "forbidden_action", "status"):
                self.assertIn(field, q["issues"][0], f"队列缺字段 {field}")
            self.assertTrue(q["issues"][0]["issue_id"].startswith("FR-01-"))

    def test_second_round_diff(self):
        """二审四分类：修复→消失；未修→保留；新增→新增；复发→回归。"""
        snap = "| 角色 | 状态 | 最后出场 |\n|---|---|---|\n| 老王 | 已死亡 | 第2章 |\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, [(1, "“好。”他说。" + "甲" * 1900),
                                  (2, "老王死了。" + "乙" * 1900),
                                  (3, "老王缓缓走来。" + "丙" * 1900)])
            (root / "mind").mkdir()
            (root / "mind" / "角色状态快照.md").write_text(snap, encoding="utf-8")
            full_review.run_review(root)
            q1 = self._queue(root)
            self.assertTrue(any("已亡角色" in i["msg"] for i in q1["issues"]))
            # 先明确登记为 fixed，再移除问题；否则“消失”不应进入回归记忆。
            for item in q1["issues"]:
                if "已亡角色" in item["msg"]:
                    item["status"] = "fixed"
            (root / "mind" / "全文审稿队列.json").write_text(json.dumps(q1, ensure_ascii=False, indent=1), encoding="utf-8")
            # 修复：第3章去掉老王
            (root / "书稿" / "第003章_章3.md").write_text("第3章 章3\n那人缓缓走来。" + "丙" * 1900, encoding="utf-8")
            full_review.run_review(root)
            q2 = self._queue(root)
            doc2 = json.loads((root / "mind" / "全文审稿队列.json").read_text(encoding="utf-8"))
            self.assertEqual(doc2["round"], 2)
            self.assertFalse(any("已亡角色" in i["msg"] for i in doc2["issues"]))
            # 复发：第4章老王再现 → 回归（resolved_log 记忆）
            (root / "书稿" / "第004章_章4.md").write_text("第4章 章4\n老王又笑了。" + "丁" * 1900, encoding="utf-8")
            full_review.run_review(root)
            q3 = self._queue(root)
            self.assertTrue(any("已亡角色" in i["msg"] for i in q3["issues"]))
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("回归", report)
            self.assertIn("新增问题：1", report)
            self.assertIn("回归问题：1", report)

    def test_length_deviation_with_functional_note(self):
        """前期加厚/功能章反例：字数偏离触发但建议含功能章豁免口径（不误伤为硬伤）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, [(i, "甲" * 2000) for i in range(1, 4)] + [(4, "乙" * 4200)])
            full_review.run_review(root)
            q = self._queue(root)
            hits = [i for i in q["issues"] if "偏离" in i["msg"]]
            self.assertTrue(hits, "2.1x 偏离应触发")
            self.assertTrue(any("功能章" in i["recommended_action"] for i in hits), "建议必须含功能章豁免口径")

    def test_low_dialog_legal(self):
        """无CP升级流反例：span≈0 不应在 full_review 被误报（full_review 只查>55 上限）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, [(1, "他想了想，没有说话。" * 80), (2, "他继续往前走，思考着。" * 80)])
            full_review.run_review(root)
            q = self._queue(root)
            self.assertFalse(any("对话占比" in i["msg"] for i in q["issues"]), "低对话章不应被告警")


class TestDowngradeRules(unittest.TestCase):
    """三处打卡式硬卡降级后的文档行为：! 级而非 ✗；台账有对应降级规则。"""

    def setUp(self):
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.ledger = (ROOT / "references" / "规则台账.md").read_text(encoding="utf-8")

    def test_rhetoric_no_minimum(self):
        row = [l for l in self.skill.splitlines() if l.startswith("| 24 |")]
        self.assertTrue(row and "| ! |" in row[0], "第24项应为警告级")
        self.assertIn("不设修辞最低数量", row[0])
        self.assertIn("RB-028", self.ledger)

    def test_aliveness_signal(self):
        row = [l for l in self.skill.splitlines() if l.startswith("| 21 |")]
        self.assertTrue(row and "| ! |" in row[0], "第21项应为警告级")
        self.assertIn("RB-029", self.ledger)

    def test_character_description_guide(self):
        row = [l for l in self.skill.splitlines() if l.startswith("| 23 |")]
        self.assertTrue(row and "| ! |" in row[0], "第23项应为警告级")
        self.assertIn("RB-030", self.ledger)

    def test_genre_exception_section(self):
        self.assertIn("题材例外优先原则", self.skill)
        for kw in ("无CP升级流低对话", "新书期前 10 章加厚", "A 级禁言词"):
            self.assertIn(kw.replace(" ", ""), self.skill.replace(" ", ""))

    def test_ledger_has_executor_and_test(self):
        import re
        rows = [l for l in self.ledger.splitlines() if re.match(r"^\| RB-\d{3} \|", l)]
        self.assertGreaterEqual(len(rows), 30)
        for r in rows:
            cells = [c.strip() for c in r.split("|")[1:-1]]
            self.assertEqual(len(cells), 11, f"字段数异常：{r[:30]}")
            self.assertTrue(cells[9] and cells[10], f"治理缺环（工具/测试为空）：{cells[0]}")


class TestTruthSourceUnity(unittest.TestCase):
    """真源统一：config 常量与常量表/代码一致；lint 全绿。"""

    def test_wall_values(self):
        self.assertEqual(config.WALL_HARD, 140)
        self.assertEqual(config.WALL_WARN, 100)
        const = (ROOT / "references" / "常量表.md").read_text(encoding="utf-8")
        self.assertIn("WALL_HARD", const)
        self.assertIn("FULL_REVIEW_DIALOG_MAX", const)

    def test_full_review_uses_config(self):
        src = (TOOLS / "full_review.py").read_text(encoding="utf-8")
        self.assertNotIn("> 55", src.replace("FULL_REVIEW_DIALOG_MAX", ""), "对话上限应引用 config 而非硬编码")
        for name in ("FULL_REVIEW_NGRAM_OVERLAP_WARN", "FULL_REVIEW_DIALOG_MAX", "FULL_REVIEW_LENGTH_HIGH_RATIO",
                     "FULL_REVIEW_LENGTH_LOW_RATIO", "FULL_REVIEW_FORESHADOW_T2", "FULL_REVIEW_FORESHADOW_T3"):
            self.assertIn(name, src)

    def test_constants_table_order(self):
        const = (ROOT / "references" / "常量表.md").read_text(encoding="utf-8")
        i8 = const.find("## 八、修改约定")
        i9 = const.find("## 九、留存分析")
        i13 = const.find("## 十三、")
        self.assertGreater(i9, i8, "「八、修改约定」应物理位于第九节之前（编号归位）")
        self.assertGreater(i13, i9)

    def test_lint_passes(self):
        r = subprocess.run([sys.executable, str(TOOLS / "lint_skill.py")], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, f"lint 应全绿：\n{r.stdout[-600:]}")

    def test_manual_versions(self):
        manifest = (ROOT / "references" / "版本台账.md").read_text(encoding="utf-8")
        self.assertIn("| references/规则台账.md | v7.38 | 核心 |", manifest)
        self.assertIn("| references/常量表.md | v7.38 | 核心 |", manifest)


class TestAntiGaming(unittest.TestCase):
    """反优化审计（机器侧）：为过检强塞导向的规则不应存在于硬卡位。"""

    def test_no_quota_words_in_hard_rules(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        # 30 项表的 ✗ 行（脚本硬卡+AI硬项）中不得出现配额式表述
        hard_rows = [l for l in skill.splitlines() if l.startswith("| ") and "| ✗" in l and l.count("|") >= 5]
        for row in hard_rows:
            for quota in ("≥3种修辞", "≥1处口头禅", "≥2特征", "外貌≤30字"):
                self.assertNotIn(quota, row, f"硬卡行仍含配额表述：{row[:60]}")

    def test_signals_describe_not_quota(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不是打卡", skill.replace("**", ""))
        self.assertIn("禁止为过检硬塞", skill.replace("**", ""))


if __name__ == "__main__":
    unittest.main(verbosity=1)