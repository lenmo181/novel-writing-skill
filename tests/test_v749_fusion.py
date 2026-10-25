# -*- coding: utf-8 -*-
"""v7.49 回归测试：三项目对标集成轮。

覆盖本轮落地的四组能力 + 一个现网崩溃修复：
  1. 期待线悬空阈值常量补齐（RB-038）——此前必崩的 NameError；
  2. 事实台账（RB-032/033/034）——登记结构 / 位置语义 / 到期必兑 / 数字事实优先登记；
  3. 证据引文不可篡改（RB-035）——服务端按 offset 逐字比对，伪造引文必须被 Gate 拦下；
  4. 伏笔到期三层提醒（RB-036）——必须回收 / 已超期 / 近期待回收；
  5. 量化 AI 味指标（RB-037）——「不是A是B」与单一意象。

断言口径与《常量表·十四》一致；常量真源在 tools/config.py。
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
# 工具之间存在同包依赖（continuity_check → project_audit 等），
# 逐个 load_mod 前先把 tools/ 加入 sys.path，否则子模块 import 失败。
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


config = load_mod("config")
continuity_check = load_mod("continuity_check")
fact_ledger = load_mod("fact_ledger")
chapter_readiness = load_mod("chapter_readiness")
review_skeleton = load_mod("review_skeleton")
check_chapter = load_mod("check_chapter")
init_project = load_mod("init_project")


LEDGER_HEADER = ("| 编号 | 事实 | 类型 | 位置 | 未知原因 | 登记章 | 到期章 | 状态 | 依据 |\n"
                 "|---|---|---|---|---|---|---|---|---|\n")


def write_ledger(root: Path, rows: str):
    (root / "mind").mkdir(parents=True, exist_ok=True)
    (root / "mind" / "事实台账.md").write_text(
        "# 事实台账\n\n" + LEDGER_HEADER + rows, encoding="utf-8")


def write_chapters(root: Path, count: int, body: str = "林舟握紧了手里的刀。这不是刀，是他的命。"):
    book = root / "书稿"
    book.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        (book / f"第{i:03d}章_测试.md").write_text(
            f"第{i}章 测试\n\n{body}\n", encoding="utf-8")


class TestExpectationConstantFixed(unittest.TestCase):
    """RB-038：期待线悬空阈值曾只写引用点未定义，含「活跃」条目即 NameError 崩溃。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novel_v749_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)

    def test_constant_exists(self):
        self.assertTrue(hasattr(config, "EXPECTATION_STALE_CHAPTERS"))
        self.assertGreater(config.EXPECTATION_STALE_CHAPTERS, 0)

    def test_active_expectation_line_does_not_crash(self):
        """活跃期待线长期未推进应告警，但绝不能抛异常（此前必 NameError 崩溃）。"""
        (self.root / "mind").mkdir(parents=True, exist_ok=True)
        (self.root / "mind" / "期待线.md").write_text(
            "| 线名 | 类型 | 建立章 | 最近推进章 | 状态 |\n|---|---|---|---|---|\n"
            "| 复仇线 | 目标牵引 | 第1章 | 第2章 | 活跃 |\n",
            encoding="utf-8")
        write_chapters(self.root, 20)
        report = continuity_check.check(self.root)
        self.assertIn("issues", report)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("EXPECTATION_STALE", codes)

    def test_fresh_expectation_no_stale_warning(self):
        (self.root / "mind").mkdir(parents=True, exist_ok=True)
        (self.root / "mind" / "期待线.md").write_text(
            "| 线名 | 类型 | 建立章 | 最近推进章 | 状态 |\n|---|---|---|---|---|\n"
            "| 复仇线 | 目标牵引 | 第1章 | 第2章 | 活跃 |\n",
            encoding="utf-8")
        write_chapters(self.root, 3)
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("EXPECTATION_STALE", codes)


class TestFactLedger(unittest.TestCase):
    """RB-032/033/034：事实台账。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novel_v749_fl_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        write_chapters(self.root, 5)

    def test_missing_ledger_reports_hint_not_crash(self):
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_LEDGER_MISSING", codes)

    def test_valid_ledger_passes(self):
        write_ledger(self.root,
                     "| FL-001 | 刀藏在床底第三块砖下 | 物品 | chapter_before:3 |  | 第1章 |  | 已登记 | 第001章 |\n"
                     "| FL-002 | 老刀欠债三百两 | 数字 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        self.assertEqual(report["issues"], [], report["issues"])
        self.assertEqual(report["stats"]["row_count"], 2)

    def test_duplicate_id_detected(self):
        write_ledger(self.root,
                     "| FL-001 | 甲事实 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n"
                     "| FL-001 | 乙事实 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_ID_DUP", codes)

    def test_position_with_chapter_parameter_accepted(self):
        write_ledger(self.root,
                     "| FL-001 | 刀在床底 | 物品 | chapter_before:3 |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        self.assertEqual(report["issues"], [], report["issues"])

    def test_position_missing_chapter_parameter_flagged(self):
        write_ledger(self.root,
                     "| FL-001 | 刀在床底 | 物品 | chapter_before |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_POSITION_BAD", codes)

    def test_unknown_position_requires_reason(self):
        write_ledger(self.root,
                     "| FL-001 | 血玉下落 | 物品 | unknown |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_UNKNOWN_REASON", codes)

    def test_unknown_position_with_valid_reason_ok(self):
        write_ledger(self.root,
                     "| FL-001 | 血玉下落 | 物品 | unknown:needs_review |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        self.assertEqual(report["issues"], [], report["issues"])

    def test_due_unpaid_detected(self):
        """到期必兑：承诺第3章兑现，当前已到第5章仍未兑现。"""
        write_ledger(self.root,
                     "| FL-001 | 刀在床底 | 物品 | chapter_before:3 |  | 第1章 | 第3章 | 待回收 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_DUE_UNPAID", codes)

    def test_due_paid_no_warning(self):
        write_ledger(self.root,
                     "| FL-001 | 刀在床底 | 物品 | chapter_before:3 |  | 第1章 | 第3章 | 已兑现 | 第003章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("FACT_DUE_UNPAID", codes)

    def test_due_not_yet_reached_no_warning(self):
        write_ledger(self.root,
                     "| FL-001 | 刀在床底 | 物品 | chapter_before:9 |  | 第1章 | 第9章 | 待回收 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("FACT_DUE_UNPAID", codes)

    def test_status_and_type_whitelist_enforced(self):
        write_ledger(self.root,
                     "| FL-001 | 甲 | 玄学 | book_start |  | 第1章 |  | 飞升 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_TYPE_UNKNOWN", codes)
        self.assertIn("FACT_STATUS_BAD", codes)

    def test_digit_fact_unregistered_detected(self):
        """数字事实优先登记：正文反复出现「三百两」但台账无此条目。"""
        body = " ".join(["老刀欠下三百两。"] * config.FACT_LEDGER_MAX_PER_CHAPTER)
        write_chapters(self.root, 5, body=body)
        write_ledger(self.root,
                     "| FL-001 | 无关事实 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_DIGIT_UNREGISTERED", codes)

    def test_digit_fact_registered_no_warning(self):
        body = "老刀欠下三百两，又欠下三百两，还要还三百两。"
        write_chapters(self.root, 5, body=body)
        write_ledger(self.root,
                     "| FL-001 | 老刀欠债三百两 | 数字 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("FACT_DIGIT_UNREGISTERED", codes)

    def test_digit_threshold_is_per_chapter(self):
        """同一数字事实跨章少量重复，不应被 MAX_PER_CHAPTER 误报。"""
        write_chapters(self.root, 5, body="老刀欠下三百两。")
        write_ledger(self.root,
                     "| FL-001 | 无关事实 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("FACT_DIGIT_UNREGISTERED", codes)

    def test_digit_threshold_flags_a_single_chapter(self):
        """单章达到阈值仍应告警，即使全书总次数没有跨章放大。"""
        body = " ".join(["老刀欠下三百两。"] * config.FACT_LEDGER_MAX_PER_CHAPTER)
        write_chapters(self.root, 5, body=body)
        write_ledger(self.root,
                     "| FL-001 | 无关事实 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n")
        report = fact_ledger.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FACT_DIGIT_UNREGISTERED", codes)
        self.assertEqual(
            report["stats"]["unregistered_digit_fact_peak_per_chapter"].get("三百两"),
            config.FACT_LEDGER_MAX_PER_CHAPTER,
        )

    def test_tool_is_read_only(self):
        """只读承诺：跑完检查后台账文件内容不得改变。"""
        rows = "| FL-001 | 刀在床底 | 物品 | book_start |  | 第1章 |  | 已登记 | 第001章 |\n"
        write_ledger(self.root, rows)
        path = self.root / "mind" / "事实台账.md"
        before = path.read_text(encoding="utf-8")
        fact_ledger.check(self.root)
        self.assertEqual(path.read_text(encoding="utf-8"), before)


class TestEvidenceQuoteUntamperable(unittest.TestCase):
    """RB-035：证据引文不可篡改（对标 AI_NovelGenerator CHAPTER_CHECK_QUOTE_MISMATCH）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novel_v749_q_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        write_chapters(self.root, 2, body="林舟握紧了手里的刀。这不是刀，是他的命。")
        (self.root / "mind" / "审校").mkdir(parents=True, exist_ok=True)

    def _write_review(self, quote, offset, status="pass"):
        path = self.root / "mind" / "审校" / "第001章审校.json"
        checks = {}
        for num in range(14, 31):
            checks[str(num)] = {
                "status": status,
                "evidence": {"text": "证据描述", "quote": quote, "offset": offset},
                "location": "",
                "confidence": 0.9,
                "note": "",
            }
        path.write_text(json.dumps({
            "version": config.SKILL_VERSION,
            "chapter": 1,
            "chapter_sha256": chapter_readiness.hashlib.sha256(
                (self.root / "书稿" / "第001章_测试.md").read_bytes()).hexdigest(),
            "checks": checks,
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def test_verify_quote_accepts_exact_match(self):
        text = "林舟握紧了手里的刀"
        ok, detail = chapter_readiness.verify_quote(text, text, 0)
        self.assertTrue(ok, detail)

    def test_verify_quote_rejects_wrong_text(self):
        ok, _ = chapter_readiness.verify_quote("林舟握紧了手里的刀", "林舟掏出三两黄金", 0)
        self.assertFalse(ok)

    def test_verify_quote_rejects_wrong_offset(self):
        ok, _ = chapter_readiness.verify_quote("林舟握紧了手里的刀", "林舟握紧了手里的刀", 3)
        self.assertFalse(ok)

    def test_verify_quote_rejects_out_of_range(self):
        ok, _ = chapter_readiness.verify_quote("短文本", "引文", 99)
        self.assertFalse(ok)

    def test_verify_quote_rejects_negative_offset(self):
        ok, _ = chapter_readiness.verify_quote("林舟", "林舟", -1)
        self.assertFalse(ok)

    def test_gate_passes_with_correct_quote(self):
        self._write_review("林舟握紧了手里的刀", 8)
        gate = chapter_readiness.semantic_gate(self.root, 1)
        self.assertTrue(gate["ok"], gate.get("tail"))

    def test_gate_blocks_fabricated_quote(self):
        """AI 编造的原文引文必须被拦下——这是本次集成的核心安全断言。"""
        self._write_review("林舟掏出了三两黄金", 8)
        gate = chapter_readiness.semantic_gate(self.root, 1)
        self.assertFalse(gate["ok"])
        self.assertTrue(any("引文与正文不符" in line for line in gate["tail"]), gate.get("tail"))

    def test_gate_blocks_quote_without_offset(self):
        self._write_review("林舟握紧了手里的刀", None)
        gate = chapter_readiness.semantic_gate(self.root, 1)
        self.assertFalse(gate["ok"])

    def test_find_quote_returns_offsets(self):
        text = "林舟握紧了手里的刀。"
        offsets = review_skeleton.find_quote(text, "林舟握紧了手里的刀")
        self.assertEqual(offsets, [0])
        self.assertEqual(review_skeleton.find_quote(text, "不存在的片段"), [])


class TestForeshadowThreeTierReminder(unittest.TestCase):
    """RB-036：伏笔到期三层提醒（对标 MuMuAINovel）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novel_v749_fs_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        write_chapters(self.root, 10)
        (self.root / "mind").mkdir(parents=True, exist_ok=True)

    def _write(self, rows):
        (self.root / "mind" / "伏笔追踪表.md").write_text(
            "| 编号 | 伏笔内容 | 埋设章 | 预计回收章 | Tier | 状态 |\n|---|---|---|---|---|---|\n" + rows,
            encoding="utf-8")

    def test_overdue_detected(self):
        self._write("| F-001 | 老刀的断指 | 第1章 | 第5章 | T2 | 未回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FORESHADOW_OVERDUE", codes)

    def test_due_detected(self):
        self._write("| F-001 | 老刀的断指 | 第1章 | 第10章 | T2 | 未回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FORESHADOW_DUE", codes)

    def test_due_soon_detected(self):
        self._write("| F-001 | 老刀的断指 | 第1章 | 第12章 | T2 | 未回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FORESHADOW_DUE_SOON", codes)

    def test_resolved_foreshadow_not_flagged(self):
        """已回收伏笔不参与到期提醒——否则会对已兑现的伏笔催债。"""
        self._write("| F-001 | 老刀的断指 | 第1章 | 第3章 | T2 | 已回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        for code in ("FORESHADOW_DUE", "FORESHADOW_OVERDUE", "FORESHADOW_DUE_SOON"):
            self.assertNotIn(code, codes)

    def test_partial_recovery_still_tracked(self):
        self._write("| F-001 | 老刀的断指 | 第1章 | 第3章 | T2 | 部分回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("FORESHADOW_OVERDUE", codes)

    def test_status_whitelist_extended(self):
        self._write("| F-001 | 老刀的断指 | 第1章 | 第30章 | T2 | 部分回收 |\n")
        report = continuity_check.check(self.root)
        codes = {i["code"] for i in report["issues"]}
        self.assertNotIn("FORESHADOW_STATUS", codes)


class TestQuantifiedAiTasteMetrics(unittest.TestCase):
    """RB-037：量化 AI 味指标（「不是A是B」与单一意象）。"""

    def test_contrast_pattern_counted(self):
        body = "这不是刀，是他的命。那不是山，是墙。"
        self.assertGreaterEqual(check_chapter.count_contrast_patterns(body), 2)

    def test_plain_sentence_has_no_contrast(self):
        self.assertEqual(check_chapter.count_contrast_patterns("林舟握紧了手里的刀。"), 0)

    def test_repeated_imagery_counted(self):
        body = "月光洒在刀上。月光落在雪里。月光沉进水底。"
        repeated = check_chapter.count_repeated_imagery(body)
        self.assertTrue(any(w == "月光" for w, _ in repeated), repeated)

    def test_single_imagery_not_flagged(self):
        body = "月光洒在刀上。林舟握紧了手里的刀。"
        self.assertEqual(check_chapter.count_repeated_imagery(body), [])

    def test_constants_in_config(self):
        self.assertEqual(config.AI_TASTE_CONTRAST_MAX, 2)
        self.assertEqual(config.AI_TASTE_IMAGERY_MAX_PER_K, 1)


class TestInitProjectRegistersFactLedger(unittest.TestCase):
    """init_project 必须生成 mind/事实台账.md，且不破坏既有档案。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="novel_v749_init_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp) / "测试书"

    def test_fact_ledger_created(self):
        init_project.init_project(self.root, "测试书")
        path = self.root / "mind" / "事实台账.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("编号", text)
        self.assertIn("事实", text)
        self.assertIn("到期章", text)

    def test_context_pack_includes_fact_ledger(self):
        init_project.init_project(self.root, "测试书")
        self.assertIn("mind/事实台账.md", load_mod("context_pack").CANONICAL_FILES)


if __name__ == "__main__":
    unittest.main()
