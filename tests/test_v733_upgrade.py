# -*- coding: utf-8 -*-
"""v7.33 升级回归测试：full_review 流水线、ai-lite 结构维、规则台账、钩子五槽、
AI味八维、P0-P3 口径、知识库 R7 入册、常量表/代码阈值一致性。"""
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_chapter = load_mod("check_chapter")
full_review = load_mod("full_review")


def make_project(tmp, chapters, snapshots=None, foreshadow=None, rhythm=None):
    root = Path(tmp)
    book = root / "书稿"
    book.mkdir(parents=True, exist_ok=True)
    for num, name, body in chapters:
        (book / f"第{num:03d}章_{name}.md").write_text(f"第{num}章 {name}\n{body}", encoding="utf-8")
    mind = root / "mind"
    mind.mkdir(exist_ok=True)
    if snapshots is not None:
        (mind / "角色状态快照.md").write_text(snapshots, encoding="utf-8")
    if foreshadow is not None:
        (mind / "伏笔追踪表.md").write_text(foreshadow, encoding="utf-8")
    if rhythm is not None:
        (mind / "章节目录.md").write_text(rhythm, encoding="utf-8")
    return root


class TestFullReview(unittest.TestCase):
    def test_p0_gap_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, [(1, "开局", "甲" * 1900), (3, "跳号", "乙" * 1900)])
            code = full_review.run_review(root)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("章节号断档", report)
            self.assertIn("P0", report)
            self.assertEqual(code, 0)  # 非 strict：报告不熔断

    def test_p0_dead_revival_and_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                [(1, "开端", "甲" * 1900), (2, "身死", "老王死了。" + "乙" * 1900),
                 (3, "回魂", "老王缓缓走来。" + "丙" * 1900), (4, "再见", "老王笑了。" + "丁" * 1900)],
                snapshots="| 角色 | 状态 | 最后出场 |\n|---|---|---|\n| 老王 | 已死亡 | 第2章 |\n",
            )
            code = full_review.run_review(root, strict=True)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("已亡角色", report)
            self.assertEqual(code, 1)  # strict 下 P0 → 退出码 1

    def test_rhythm_streak_and_foreshadow_sleep(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                [(i, f"章{i}", "甲" * 1900) for i in range(1, 6)],
                rhythm="| 章号 | 节奏类型 |\n|---|---|\n" + "".join(f"| 第{i}章 | 主线 |\n" for i in range(1, 6)),
            )
            full_review.run_review(root)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("连续 5 章", report)           # 节奏同型连续 ≥3

    def test_foreshadow_sleep_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 22 章小文件（避开字数偏离检查的 med≥1500 门槛），F01 最后推进第1章 → 21>20 触发沉睡
            root = make_project(
                tmp,
                [(i, f"章{i}", "内容各不相同" * 3 + "尾" * i) for i in range(1, 23)],
                foreshadow="| 编号 | Tier | 状态 | 最后推进 |\n|---|---|---|---|\n| F01 | Tier-3 | 进行中 | 第1章 |\n",
            )
            full_review.run_review(root)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("疑似沉睡", report)

    def test_foreshadow_threshold_not_overfired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(
                tmp,
                [(i, f"章{i}", "甲" * 1900) for i in range(1, 5)],
                foreshadow="| 编号 | Tier | 状态 | 最后推进 |\n|---|---|---|---|\n| F01 | Tier-3 | 进行中 | 第3章 |\n",
            )
            full_review.run_review(root)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertNotIn("疑似沉睡", report)         # 4-3=1 < 20：不误报

    def test_clean_project_reports_zero_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp, [(1, "起", "甲" * 1900), (2, "承", "乙" * 1900)])
            code = full_review.run_review(root, strict=True)
            self.assertEqual(code, 0)
            report = (root / "mind" / "全文审稿报告.md").read_text(encoding="utf-8")
            self.assertIn("P0×0", report)

    def test_empty_project_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(full_review.run_review(Path(tmp)), 2)


class TestAiLiteStructural(unittest.TestCase):
    def test_dup5_flagged_and_clamped(self):
        para = "他缓缓抬起头，目光扫过众人，然后又缓缓坐下。" * 6
        score, reasons, metrics = check_chapter.ai_lite_score(para, [para] * 3)
        self.assertTrue(any("5-gram" in r for r in reasons))
        self.assertGreater(metrics["dup5_pct"], 2)
        self.assertLessEqual(score, 10)

    def test_normal_text_not_flagged(self):
        body = ("陆鸣睁开眼，鼻息间似有雷火气流涌动。院外传来嘈杂的脚步声，他把窗户关上，"
                "坐回桌前继续擦拭那柄旧刀。刀身映出他自己的眼睛。他没有说话，只是又擦了一遍。"
                "远处有人敲钟，第三下之后，一切归于安静。")
        lines = [body[i:i + 40] for i in range(0, len(body), 40)]
        score, reasons, metrics = check_chapter.ai_lite_score(body, lines)
        self.assertNotIn("章内5-gram", "；".join(reasons))
        self.assertLess(metrics["dup5_pct"], 2)

    def test_ai_lite_cli_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "第001章_试.md"
            f.write_text("第1章 试\n“你好。”他答。随后院外传来三声钟响，惊起一群飞鸟，落在远处的屋脊上。", encoding="utf-8")
            r = subprocess.run([sys.executable, str(TOOLS / "check_chapter.py"), "--ai-lite", str(f)],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0)
            self.assertIn("AI味粗测", r.stdout)


class RuleDocs(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.ledger = (ROOT / "references" / "规则台账.md").read_text(encoding="utf-8")
        self.kb = (ROOT / "references" / "热榜知识库.md").read_text(encoding="utf-8")
        self.deai = (ROOT / "references" / "去AI味.md").read_text(encoding="utf-8")
        self.health = (ROOT / "references" / "体检.md").read_text(encoding="utf-8")
        self.const = (ROOT / "references" / "常量表.md").read_text(encoding="utf-8")
        self.research = (ROOT / "references" / "热榜研究.md").read_text(encoding="utf-8")

    def test_ledger_entries(self):
        ids = re.findall(r"\| (RB-\d{3}) \|", self.ledger)
        self.assertGreaterEqual(len(ids), 25)
        self.assertEqual(len(ids), len(set(ids)), "RB 编号不得重复")
        for state in re.findall(r"\| (候选|实验|稳定|修正|废弃) \|", self.ledger):
            self.assertIn(state, ("候选", "实验", "稳定", "修正", "废弃"))

    def test_hook_five_slots(self):
        self.assertIn("载体-动作-对象-信息性质-后果", self.skill)
        self.assertIn("防提前消耗", self.skill)

    def test_ai_flavor_8dims(self):
        for dim in ("语言AI味", "情绪AI味", "对话AI味", "节奏AI味", "结构AI味", "视角AI味", "解释AI味", "重复AI味"):
            self.assertIn(dim, self.deai)
        self.assertIn("5-gram", self.deai)

    def test_p0_p3_alignment(self):
        for lv in ("P0", "P1", "P2", "P3"):
            self.assertIn(lv, self.health)
        self.assertIn("十三、全文审稿", self.const)
        self.assertIn("40%", self.const)

    def test_kb_r7(self):
        self.assertIn("轮次7", self.kb)
        self.assertIn("21 本 31 题材", self.kb)
        for t in ("传统玄幻", "都市种田", "快穿", "游戏体育"):
            self.assertIn(t, self.kb)

    def test_evidence_levels(self):
        self.assertIn("官方数据+多作品", self.research)
        self.assertIn("个人推测/未验证", self.research)
        self.assertIn("D 级绝不直接写入核心硬规则", self.research)

    def test_routing_rows(self):
        self.assertIn("全文审稿", self.skill)
        self.assertIn("规则台账", self.skill)

    def test_version(self):
        from config import SKILL_VERSION, RELEASE_DATE
        self.assertEqual(SKILL_VERSION, "7.35")
        self.assertEqual(RELEASE_DATE, "2026-09-30")
        self.assertTrue("v7.35" in self.skill or "v7.33" in self.skill)

    def test_constants_code_consistency(self):
        # v7.34 起阈值移入 config（本测试原为文本断言，按治理要求改由行为测试覆盖：
        # 见 test_v734_governance.TestFullReviewThresholds / TestTruthSourceUnity）
        import config as _cfg
        for name, val in (("FULL_REVIEW_NGRAM_OVERLAP_WARN", 40), ("FULL_REVIEW_DIALOG_MAX", 55),
                          ("FULL_REVIEW_LENGTH_HIGH_RATIO", 1.6), ("FULL_REVIEW_LENGTH_LOW_RATIO", 0.55),
                          ("FULL_REVIEW_FORESHADOW_T2", 40), ("FULL_REVIEW_FORESHADOW_T3", 20)):
            self.assertEqual(getattr(_cfg, name), val)


if __name__ == "__main__":
    unittest.main(verbosity=1)
