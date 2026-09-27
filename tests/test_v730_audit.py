# -*- coding: utf-8 -*-
"""
v7.30 第三轮审计修复回归测试（unittest，纯标准库，tempfile 夹具，不碰真实书稿）
运行：python -m unittest discover -s tests -p "test_*.py"
覆盖：
  fix_said_tags —— 介词/否定修饰语保守保留（防「他对她。」残句与语义反转）、
                   GBK 章受控跳过、原子写回无 .tmpfix 残留、BOM 首行、walls 切点句号后紧跟引号可切
  grep_consistency —— A 类按「最后出场之后」取窗口（长书早期死亡复活不再漏检）、
                   最后出场缺失降级提示（不逐章误报）、--limit 0 不再切片成全书
  check_chapter —— --dialog-max 0 不触发「偏高」警告、# 标题按章节标题剔除、BOM 剥离
  zhuque —— labels_ratio 缺键按检测失败（不再默认 0 误判禁止交付）、删章后幽灵旧行剔除
  mochi —— score 缺 total/五维键按检测失败
  conflict_score —— 峰值间距乱序输入先排序（不再伪告警/漏报）
  project_audit —— 中文数字章号 + 「回」体文件名/标题行识别
  visualize —— read_text 编码坏点不崩、阅读进度键按绝对路径隔离
  update_skill —— replace_skill 回滚失败不掩盖原始异常
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock as mock
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclass（update_skill.Release）解析需要模块已注册
    spec.loader.exec_module(mod)
    return mod


fix = load_mod("fix_said_tags")
chk = load_mod("check_chapter")
gc = load_mod("grep_consistency")
zhu = load_mod("zhuque_check")
mochi = load_mod("mochi_check")
cs = load_mod("conflict_score")
pa = load_mod("project_audit")
viz = load_mod("visualize")


class TempCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="novel_v729_")
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)


# ─────────────────────── fix_said_tags：修饰语收紧 + 编码/写回防线 ───────────────────────

class TestFixSaidTags(TempCase):
    def test_prepositional_phrase_kept_verbatim(self):
        # 此前「对她说」的「对她」被当修饰语，动词「说」被删产出「他对她。」残句
        line = "“我走了。”他对她说，“你保重。”"
        self.assertEqual(fix.process_line(line, [0, 0, 0, 0]), line)

    def test_negation_not_inverted(self):
        # 此前「没说什么」→「他没什么。」语义反转
        line = "“嗯。”他没说什么，“哦。”"
        self.assertEqual(fix.process_line(line, [0, 0, 0, 0]), line)

    def test_genuine_modifier_still_beats(self):
        out = fix.process_line("“我走了。”他压低声音说，“你保重。”", [0, 0, 0, 0])
        self.assertIn("他压低声音。", out)

    def test_bare_tag_still_removed(self):
        out = fix.process_line("“我走了。”他又说，“你保重。”", [0, 0, 0, 0])
        self.assertNotIn("他又说", out)

    def test_gbk_file_skipped_untouched(self):
        p = os.path.join(self.td, "第1章_g.md")
        raw = "“你好。”他说。".encode("gbk")
        with open(p, "wb") as f:
            f.write(raw)
        r = fix.process(p, False, None, False, False)
        self.assertEqual(r, (0, 0, 0, 0, 0, 0, False))
        with open(p, "rb") as f:
            self.assertEqual(f.read(), raw)  # 非 UTF-8 原文一字节不动

    def test_atomic_write_no_tmp_residue(self):
        p = os.path.join(self.td, "第2章_ok.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("他说：“走。”")
        r = fix.process(p, False, None, False, False)
        self.assertTrue(r[6])
        self.assertEqual([n for n in os.listdir(self.td) if n.endswith(".tmpfix")], [])
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "“走。”")

    def test_bom_first_line_tag_fixed(self):
        p = os.path.join(self.td, "第3章_bom.md")
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write("他说：“走。”")
        fix.process(p, False, None, False, False)
        with open(p, encoding="utf-8-sig") as f:
            self.assertEqual(f.read().strip(), "“走。”")  # BOM 不再让首行 ^锚定失效

    def test_walls_cut_before_opening_quote(self):
        # 句号后紧跟 “：切点应判在标点本身（引号外），合法切点不再被误拒。
        # 前段 5×16=80 字无句界 + 句号 + 引号对白 + 后段 2×27 字收尾 → 全长 >140，
        # 「句号+“」是 mid±60 窗口内唯一切点：旧逻辑误拒 → 整行不拆；新逻辑拆开。
        ln = ("他把能想起来的细节又重新过了一遍" * 6) + "。" + "“等等。”" \
             + ("此后一路无话风声渐大天色暗尽他们摸黑走完最后一段山路" * 2) + "。"
        self.assertGreater(len(ln), 140)
        p = os.path.join(self.td, "第4章_w.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(ln)
        fix.process(p, False, None, True, False)
        with open(p, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("\n", body)
        second = [s for s in body.split("\n") if s.strip()][1]
        self.assertTrue(second.startswith("“"))


# ─────────────────────── grep_consistency：A 类窗口 + 档案不全降级 ───────────────────────

def make_book(td, n_ch, dead_revive_at=None, dead="李四", last_field="第1章"):
    """造 n_ch 章的书 + 一个已亡角色；dead_revive_at 章正文让该角色复活。"""
    book = os.path.join(td, "书稿")
    mind = os.path.join(td, "mind")
    os.makedirs(book, exist_ok=True)
    os.makedirs(mind, exist_ok=True)
    for i in range(1, n_ch + 1):
        body = f"{dead}出现了。" if i == dead_revive_at else "路人甲赶路。"
        with open(os.path.join(book, f"第{i}章_试.md"), "w", encoding="utf-8") as f:
            f.write(f"第{i}章 试\n\n{body}\n")
    with open(os.path.join(mind, "角色状态快照.md"), "w", encoding="utf-8") as f:
        f.write(f"# 角色状态快照\n\n## {dead}\n- 状态：已亡\n- 最后出场：{last_field}\n")
    return book, mind


class TestGrepConsistency(TempCase):
    def test_early_revival_caught_outside_tail_window(self):
        # 5 章书 limit=2：尾部窗口只有第4-5章，角色第1章死第3章复活——
        # 旧实现窗口取全书尾部 → 漏检；新实现按「最后出场(1)+1」起扫 → 抓到第3章
        make_book(self.td, 5, dead_revive_at=3)
        issues = gc.scan(self.td, 2)
        high = [i for i in issues if i[0] == "A" and i[1] == "高"]
        self.assertEqual(len(high), 1)
        self.assertIn("第3章", high[0][3])

    def test_missing_last_chapter_downgraded_not_spammed(self):
        # 最后出场写「第十章」（A 类不解析中文数字）→ 一条低级档案提示，不逐章高级误报
        make_book(self.td, 3, last_field="第十章")
        issues = gc.scan(self.td, 200)
        a = [i for i in issues if i[0] == "A"]
        self.assertEqual(len([i for i in a if i[1] == "高"]), 0)
        self.assertEqual(len([i for i in a if i[1] == "低"]), 1)

    def test_limit_zero_scans_nothing_for_a(self):
        make_book(self.td, 3, dead_revive_at=2)
        issues = gc.scan(self.td, 0)
        self.assertEqual([i for i in issues if i[0] == "A" and i[1] == "高"], [])


# ─────────────────────── check_chapter：dialog-max 0 + # 标题 + BOM ───────────────────────

class TestCheckChapter(TempCase):
    def test_dialog_max_zero_no_false_high_warning(self):
        # --dialog-max 0 传 0 关闭上限：此前 0-5=-5，ratio≥25 全部落入「偏高」荒谬警告
        p = os.path.join(self.td, "第1章_d.md")
        dialog = "“你要去哪。”" * 20  # 拉高对话占比到 25% 以上
        with open(p, "w", encoding="utf-8") as f:
            f.write("第1章 试\n\n" + dialog + "他往前走了一段很长的路。\n")
        buf = StringIO()
        with redirect_stdout(buf):
            chk.check(p, 100, 10000, "chal", 15, 0)
        self.assertNotIn("偏高", buf.getvalue())

    def test_hash_title_stripped_as_title(self):
        lines, dropped = chk.body_lines("# 第3章 落水\n\n正文第一行。")
        self.assertEqual(lines, ["正文第一行。"])
        self.assertTrue(dropped and dropped[0].startswith("章节标题"))

    def test_bom_stripped_by_load_text(self):
        p = os.path.join(self.td, "第5章_b.md")
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write("第5章 试\n\n正文。\n")
        text = chk.load_text(p)
        self.assertFalse(text.startswith("﻿"))  # BOM 已剥离，TITLE_RE 可命中
        lines, _ = chk.body_lines(text)
        self.assertEqual(lines, ["正文。"])


# ─────────────────────── zhuque：缺键防线 + 幽灵章 ───────────────────────

def zhu_resp():
    return {"status": "success",
            "labels_ratio": {"0": 0.95, "1": 0.02, "2": 0.01},
            "segment_labels": []}


def run_zhu_book(book, only=""):
    args = SimpleNamespace(book=str(book), only=only, threshold=90.0, warn=80.0,
                           segments=0, no_merge=True, timeout=5, delay=0)
    with mock.patch.object(zhu, "call_api", return_value=zhu_resp()):
        return zhu.run_book(args, key="k")


class TestZhuque(TempCase):
    def test_ratio_missing_key_raises(self):
        with self.assertRaises(ValueError):
            zhu._ratio_pct({"1": 0.3}, "0")  # 缺 "0" 键不再默认 0 → 检测失败

    def test_ratio_null_value_raises(self):
        with self.assertRaises(ValueError):
            zhu._ratio_pct({"0": None}, "0")

    def test_ghost_chapter_rows_dropped(self):
        book = Path(self.td) / "书"
        (book / "书稿").mkdir(parents=True)
        for n in (1, 2, 3):
            (book / "书稿" / f"第{n:03d}章_试.md").write_text(
                "第%d章 试\n\n" % n + "他往前走。她也在。" * 30, encoding="utf-8")
        self.assertEqual(run_zhu_book(book), 0)
        # 删掉第3章，只重测第1章：第3章旧行必须剔除，退出码不能再被幽灵行卡住
        (book / "书稿" / "第003章_试.md").unlink()
        rc = run_zhu_book(book, only="1")
        self.assertEqual(rc, 0)
        report = (book / "mind" / "朱雀检测报告.md").read_text(encoding="utf-8")
        self.assertNotIn("| 3 |", report)


# ─────────────────────── mochi：缺键防线 ───────────────────────

class TestMochiScore(TempCase):
    def _chapter(self):
        p = os.path.join(self.td, "第1章_a.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("第1章 甲\n\n" + "他往前走。她也在。" * 30)
        return p

    def test_analyze_one_missing_total(self):
        # 此前 sc.get("total", 0) 缺键 → 0 分误判不达标；现按检测失败
        fake = {"chapters": [{"score": {"real": 5.0, "human": 5.0, "imm": 5.0, "rhy": 5.0, "syn": 5.0}}]}
        with mock.patch.object(mochi, "call_analyze", return_value=fake):
            row, err = mochi.analyze_one("http://x", self._chapter(), 3, 5)
        self.assertIsNone(row)
        self.assertIn("total", err)

    def test_analyze_one_missing_dim(self):
        fake = {"chapters": [{"score": {"total": 6.0, "real": 5.0}}]}
        with mock.patch.object(mochi, "call_analyze", return_value=fake):
            row, err = mochi.analyze_one("http://x", self._chapter(), 3, 5)
        self.assertIsNone(row)
        self.assertIn("五维", err)


# ─────────────────────── conflict_score：峰值间距排序 ───────────────────────

class TestConflictScore(unittest.TestCase):
    def test_peak_spacing_out_of_order_input(self):
        # 乱序输入先按章号排序再比对：不再产生负间距伪告警，也不再漏报真告警
        self.assertEqual(cs.check_peak_spacing([(12, 20), (5, 20)]), [])        # 间距7 ≥ gap4
        self.assertEqual(cs.check_peak_spacing([(8, 20), (5, 20)]), [(5, 8)])   # 间距3 < gap4


# ─────────────────────── project_audit：中文数字 + 回体 ───────────────────────

class TestProjectAudit(unittest.TestCase):
    def test_cn_numeral_filenames(self):
        self.assertEqual(pa.parse_chapter_filename(Path("第十二章_风起.md")), (12, "风起"))
        self.assertEqual(pa.parse_chapter_filename(Path("第三十二回_旧事.md")), (32, "旧事"))
        self.assertEqual(pa.parse_chapter_filename(Path("第10章_x.md")), (10, "x"))
        self.assertIsNone(pa.parse_chapter_filename(Path("番外.md")))

    def test_cn_numeral_title_line(self):
        p = Path(tempfile.mkdtemp(prefix="novel_v729_t_")) / "第十二章_风起.md"
        p.write_text("# 第十二章 风起\n\n正文。", encoding="utf-8")
        try:
            self.assertEqual(pa.parse_title_line(p), (12, "风起"))
        finally:
            shutil.rmtree(p.parent, ignore_errors=True)


# ─────────────────────── visualize：编码容错 + 阅读键隔离 ───────────────────────

class TestVisualize(TempCase):
    def test_read_text_survives_bad_encoding(self):
        p = os.path.join(self.td, "gbk.md")
        with open(p, "wb") as f:
            f.write("“你好.”".encode("gbk"))
        # GBK 字节流按 utf-8-sig+replace 读不崩、返回字符串（errors=replace 兜底）
        self.assertIsInstance(viz.read_text(p), str)

    def test_readkey_isolated_by_abspath(self):
        # 同名项目在不同父目录下，阅读进度键必须不同（此前只用 basename 互相污染）
        keys = []
        for sub in ("书A", "书B"):
            root = os.path.join(self.td, sub, "测试书")
            os.makedirs(os.path.join(root, "书稿"), exist_ok=True)
            os.makedirs(os.path.join(root, "mind"), exist_ok=True)
            with open(os.path.join(root, "书稿", "第1章_试.md"), "w", encoding="utf-8") as f:
                f.write("第1章 试\n\n正文。\n")
            with open(os.path.join(root, "mind", "角色状态快照.md"), "w", encoding="utf-8") as f:
                f.write("# 角色状态快照\n")
            data = viz.collect(root)
            self.assertTrue(data["rdkey"].startswith("kbRead::测试书::"))
            keys.append(data["rdkey"])
        self.assertNotEqual(keys[0], keys[1])


# ─────────────────────── update_skill：回滚不掩盖原始异常 ───────────────────────

class TestUpdateSkill(TempCase):
    def test_replace_skill_rollback_failure_keeps_original_error(self):
        upd = load_mod("update_skill")
        cand = Path(self.td) / "cand"
        cand.mkdir()
        (cand / "SKILL.md").write_text("v9.99", encoding="utf-8")
        dest = Path(self.td) / "dest"
        dest.mkdir()
        (dest / "SKILL.md").write_text("v1.00", encoding="utf-8")
        backup_root = Path(self.td) / "bak"

        def flaky_copy(src, dst):
            raise PermissionError("locked")

        with mock.patch.object(upd, "_copy_tree", side_effect=flaky_copy):
            with self.assertRaises(PermissionError):
                upd.replace_skill(cand, dest, backup_root)
        # 原始异常类型保留（回滚失败不掩盖）


if __name__ == "__main__":
    unittest.main()
