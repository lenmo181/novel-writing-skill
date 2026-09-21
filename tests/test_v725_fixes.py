# -*- coding: utf-8 -*-
"""
v7.25 修复回归测试（unittest，纯标准库，全部用 tempfile 夹具，不碰真实书稿）
运行：python -m unittest discover -s tests -p "test_*.py"
覆盖：fix_said_tags 防丢文/备份、朱雀/墨尺检测防线、check_chapter 补盲、剧本暗道、
留存空文、冲突类型、封面结构校验、引用根目录、节奏告警去重、目录待办、看板修复。
"""
import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fix = load_mod("fix_said_tags")
chk = load_mod("check_chapter")
gen = load_mod("gen_index")
grep = load_mod("grep_consistency")
refs = load_mod("check_refs")
conf = load_mod("conflict_score")
cover = load_mod("cover_check")
vis = load_mod("visualize")
zhu = load_mod("zhuque_check")
mochi = load_mod("mochi_check")

ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_tool(tool, *args):
    return subprocess.run(
        [sys.executable, "-B", str(TOOLS / tool), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)


def make_png(w, h):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ─────────────────────────── 通用章节夹具（可通过 check_chapter 基线） ───────────────────────────

NARR_A = "巷子深处没有灯，林舟数着自己的脚步声往前走，把铜钥匙贴着掌心攥出了汗{i}。"
NARR_B = "他停在三号门前，先看门缝，再听屋里的动静，最后才把整个身子贴上冰冷的砖墙{i}。"
DIAL_A = "“先别敲门，灯还亮着，里面的人还没睡{i}。”沈宁压着嗓子说完，把他往阴影里拽了半步{i}。"
DIAL_B = "“你数到三十就动手{i}。”林舟应了一声，盯着那扇门，手心的汗又添了一层{i}。"


def base_chapter_text():
    paras = ["第1章 试探", ""]
    for i in range(1, 60):
        if i % 2 == 1:
            paras.append((NARR_A if i % 4 == 1 else NARR_B).format(i=i))
        else:
            paras.append((DIAL_A if i % 4 == 0 else DIAL_B).format(i=i))
        paras.append("")
    return "\n".join(paras)


class TempCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="novel_v725_")
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)


# ─────────────────────────── fix_said_tags：防丢文 + 备份不覆盖 ───────────────────────────

class TestFixSaidTags(TempCase):
    def test_suffix_keeps_trailing_narration(self):
        out = fix.process_line("他说：“走吧。”他把钥匙交给我，转身走进雨里。", [0, 0, 0, 0])
        self.assertEqual(out, "“走吧。”他把钥匙交给我，转身走进雨里。")

    def test_prefix_with_modifier_keeps_tail(self):
        out = fix.process_line("他压低声音说：“走吧。”他把钥匙交给我。", [0, 0, 0, 0])
        self.assertEqual(out, "他压低声音。“走吧。”他把钥匙交给我。")

    def test_end_tag_and_untouched_line(self):
        stat = [0, 0, 0, 0]
        self.assertEqual(fix.process_line("“走吧。”他说。", stat), "“走吧。”")
        self.assertEqual(stat[1], 1)
        plain = "他沿着湿滑的石阶走过去，没有回头。"
        self.assertEqual(fix.process_line(plain, [0, 0, 0, 0]), plain)

    def test_backup_not_overwritten_on_second_run(self):
        book = Path(self.td) / "书稿"
        book.mkdir()
        f = book / "第001章_试.md"
        original = "第1章 试\n\n他说：“走吧。”他把钥匙交给我。\n更新时间：2026-09-22\n"
        f.write_text(original, encoding="utf-8")
        backup_dir = os.path.join(self.td, "mind", "大修备份", "修复原稿")
        fix.process(str(f), False, backup_dir, False, False, skip_tags=False)
        plain_backup = Path(backup_dir) / f.name
        self.assertEqual(plain_backup.read_text(encoding="utf-8"), original)
        fix.process(str(f), False, backup_dir, False, True, skip_tags=False)
        backups = sorted(Path(backup_dir).iterdir())
        self.assertGreaterEqual(len(backups), 2)  # 首轮备份 + 第二轮时间戳副本
        self.assertEqual(plain_backup.read_text(encoding="utf-8"), original)
        self.assertIn("更新时间", backups[1].read_text(encoding="utf-8"))
        self.assertNotIn("他说：", f.read_text(encoding="utf-8"))


# ─────────────────────────── check_chapter：后缀他说 + 标题误剔 ───────────────────────────

class TestCheckChapter(TempCase):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.td, "第001章_试探.md")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(base_chapter_text())

    def test_baseline_passes(self):
        r = run_tool("check_chapter.py", self.path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_suffix_said_tags_now_counted(self):
        with open(self.path, "a", encoding="utf-8") as fh:
            for i in range(6):
                fh.write(f"“把灯关上{i}。”他说。\n")
        r = run_tool("check_chapter.py", self.path)
        self.assertEqual(r.returncode, 1)
        self.assertIn("光杆引导", r.stdout)

    def test_body_line_starting_with_hui_not_stripped(self):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("第三回交手，他仿佛摸清了对手的路数。\n")
        r = run_tool("check_chapter.py", self.path)
        self.assertEqual(r.returncode, 1)
        self.assertIn("A级禁言词", r.stdout)
        self.assertIn("仿佛", r.stdout)


# ─────────────────────────── 朱雀：NaN/越界、阈值、旧结论重判、分段、旧报告 ───────────────────────────

class TestZhuque(TempCase):
    def test_evaluate_rejects_nan_and_out_of_range(self):
        with self.assertRaises(ValueError):
            zhu.evaluate({"0": "NaN", "1": 0, "2": 0}, 90, 80)
        with self.assertRaises(ValueError):
            zhu.evaluate({"0": 2}, 90, 80)
        with self.assertRaises(ValueError):
            zhu.evaluate({"0": "abc"}, 90, 80)

    def test_evaluate_levels(self):
        self.assertEqual(zhu.evaluate({"0": 0.95}, 90, 80), (95.0, "pass"))
        self.assertEqual(zhu.evaluate({"0": 0.85}, 90, 80), (85.0, "warn"))
        self.assertEqual(zhu.evaluate({"0": 0.6}, 90, 80), (60.0, "fail"))

    def test_percent_arg_validation(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            zhu._percent_arg("nan")
        with self.assertRaises(argparse.ArgumentTypeError):
            zhu._percent_arg("120")
        self.assertEqual(zhu._percent_arg("90"), 90.0)

    def test_relevel_reused_rows(self):
        rows = [{"reused": True, "level": "pass", "human": 60.0},
                {"reused": True, "level": "error", "human": None}]
        zhu._relevel_reused(rows, 90, 80)
        self.assertEqual(rows[0]["level"], "fail")
        self.assertEqual(rows[1]["level"], "error")

    def test_worst_segments_tolerates_bad_entries(self):
        segs = [None, {"label": 1, "conf": 0.9, "text": "第一段", "order": 1},
                {"label": 1, "conf": "bad", "text": "第二段", "order": 2}]
        out = zhu.worst_segments(segs, 5)
        self.assertEqual(len(out), 2)
        self.assertIn("seg#1", out[0])

    def test_load_prev_report_reads_human_and_tolerates_garbage(self):
        path = os.path.join(self.td, "朱雀检测报告.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# 朱雀检测报告（轮次：2）\n\n"
                     "| 章号 | 标题 | AI% | 疑似% | 人类分 | ai_pct | 较上轮 | 结论 |\n"
                     "|---|---|---|---|---|---|---|---|\n"
                     "| 3 | 甲 | 12.0 | 8.0 | 80.0 | 20.0 | 上轮值 | 通过 |\n"
                     "| 4 | 乙 | 1..2 | x | 60.0 | 30.0 | - | 通过 |\n"
                     "| 5 | 丙 | - | - | - | - | - | 检测失败 |\n")
        rnd, prev, rows = zhu.load_prev_report(path)
        self.assertEqual(rnd, 2)
        self.assertEqual(prev[3], 80.0)          # 人类分列，而不是旧 ai_pct 列
        self.assertEqual(prev[4], 60.0)          # AI% 列损坏不影响该行
        self.assertEqual(rows[5]["level"], "error")

    def test_run_book_smoke_writes_human_report(self):
        import unittest.mock as mock
        book = Path(self.td) / "书"
        (book / "书稿").mkdir(parents=True)
        (book / "书稿" / "第001章_试.md").write_text(base_chapter_text(), encoding="utf-8")
        resp = {"status": "success", "labels_ratio": {"0": 0.95, "1": 0.03, "2": 0.02},
                "segment_labels": [None, {"label": 1, "conf": 0.9, "text": "x", "order": 1}]}
        args = SimpleNamespace(book=str(book), only="", threshold=90.0, warn=80.0,
                               segments=3, no_merge=True, timeout=5, delay=0)
        with mock.patch.object(zhu, "call_api", return_value=resp):
            rc = zhu.run_book(args, key="k")
        self.assertEqual(rc, 0)
        report = (book / "mind" / "朱雀检测报告.md").read_text(encoding="utf-8")
        self.assertIn("人类分", report)
        self.assertNotIn("ai_pct", report)
        self.assertIn("| 1 | 试 | 3.0 | 2.0 | 95.0 |", report)


# ─────────────────────────── 墨尺：缺评分/NaN、旧报告、阈值 ───────────────────────────

class TestMochi(TempCase):
    def _chapter_file(self):
        p = os.path.join(self.td, "第001章_试.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(base_chapter_text())
        return p

    def test_analyze_one_missing_score(self):
        import unittest.mock as mock
        with mock.patch.object(mochi, "call_analyze", return_value={"chapters": [{}]}):
            row, err = mochi.analyze_one("http://x", self._chapter_file(), 5, 5)
        self.assertIsNone(row)
        self.assertIn("score", err)

    def test_analyze_one_nan_and_out_of_range_total(self):
        import unittest.mock as mock
        bad = {"chapters": [{"score": {"total": "NaN", "real": 9, "human": 9,
                                       "imm": 9, "rhy": 9, "syn": 9}}]}
        with mock.patch.object(mochi, "call_analyze", return_value=bad):
            row, err = mochi.analyze_one("http://x", self._chapter_file(), 5, 5)
        self.assertIsNone(row)
        self.assertIn("0-10", err)
        over = {"chapters": [{"score": {"total": 11, "real": 9, "human": 9,
                                        "imm": 9, "rhy": 9, "syn": 9}}]}
        with mock.patch.object(mochi, "call_analyze", return_value=over):
            row, err = mochi.analyze_one("http://x", self._chapter_file(), 5, 5)
        self.assertIsNone(row)
        self.assertIn("0-10", err)

    def test_analyze_one_valid(self):
        import unittest.mock as mock
        ok = {"chapters": [{"score": {"total": 9.2, "real": 9, "human": 9,
                                      "imm": 9, "rhy": 9, "syn": 9},
                            "items": {}, "violations": 0}]}
        with mock.patch.object(mochi, "call_analyze", return_value=ok):
            row, err = mochi.analyze_one("http://x", self._chapter_file(), 5, 5)
        self.assertIsNone(err)
        self.assertEqual(row["total"], 9.2)

    def test_score_arg_validation(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            mochi._score_arg("nan")
        self.assertEqual(mochi._score_arg("8.5"), 8.5)

    def test_load_prev_tolerates_garbage(self):
        path = os.path.join(self.td, "墨尺检测报告.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# 墨尺检测报告（轮次：1）\n\n"
                     "| 章号 | 标题 | 总分 | 真人感 | 人味 | 代入感 | 节奏 | 句法 | 较上轮 | 结论 |\n"
                     "|---|---|---|---|---|---|---|---|---|---|\n"
                     "| 3 | 甲 | 6.0 | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | 上轮值 | 通过 |\n"
                     "| 4 | 乙 | 1..2 | x | x | x | x | x | - | 通过 |\n"
                     "| 5 | 丙 | - | - | - | - | - | - | - | 检测失败 |\n")
        rnd, prev, rows = mochi.load_prev_report(path)
        self.assertEqual(prev[3], 6.0)
        self.assertNotIn(4, prev)
        self.assertEqual(rows[5]["level"], "error")

    def test_relevel_reused_rows(self):
        rows = [{"reused": True, "level": "pass", "total": 6.0}]
        mochi._relevel_reused(rows, 8.0, 9.0)
        self.assertEqual(rows[0]["level"], "fail")


# ─────────────────────────── script_check：暗道实体词不误判 ───────────────────────────

SCRIPT = """第1章 潜行（改编剧本）
场景1 内景-地道口-夜
沈宁：沿着暗道走，出口就在前面。
林舟：好，你在前，我在后。
沈宁：脚步放轻，这底下回声大。
林舟：明白。
△两人俯身钻进地道，手电光压得很低。
场景2 外景-巷口-夜
林舟：到了，就是这扇门。
沈宁：敲门暗号还是老三样？
林舟：老三样，你数着。
【字幕：三分钟后】
沈宁：开门的应该是我。
林舟：为什么？
沈宁：因为钥匙在我兜里。
"""


class TestScriptCheck(TempCase):
    def _run(self, text):
        p = os.path.join(self.td, "第001章_潜行.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return run_tool("script_check.py", p)

    def test_tunnel_entity_word_passes(self):
        r = self._run(SCRIPT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("心理描写残留", r.stdout)

    def test_real_psych_still_flagged(self):
        r = self._run(SCRIPT.replace("△两人俯身钻进地道，手电光压得很低。",
                                     "△林舟心想：坏了，这地道比想的深。"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("心理描写残留", r.stdout)


# ─────────────────────────── retention_check：空文受控 ───────────────────────────

class TestRetention(TempCase):
    def _write(self, name, text):
        p = os.path.join(self.td, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def test_empty_inputs_exit_2(self):
        for text in ("", "\n\n   \n", "第1章 试探\n"):
            p = self._write("空.md", text)
            r = run_tool("retention_check.py", p)
            self.assertEqual(r.returncode, 2, (text, r.stdout, r.stderr))
            self.assertIn("输入错误", r.stdout)

    def test_empty_prev_skips_cross_analysis(self):
        cur = self._write("当前.md", base_chapter_text())
        empty = self._write("空上章.md", "第0章 空\n")
        r = run_tool("retention_check.py", cur, "--prev", empty)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("跳过跨章分析", r.stdout)

    def test_normal_chapter_exit_0(self):
        cur = self._write("正常.md", base_chapter_text())
        r = run_tool("retention_check.py", cur)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# ─────────────────────────── conflict_score：章号类型入口校验 ───────────────────────────

class TestConflictScore(TempCase):
    def test_string_chapter_controlled_error(self):
        p = os.path.join(self.td, "ch.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"chapters": [{"chapter": "1", "title": "试", "factors": []}]}, fh)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = conf.run_json(p, 1)
        self.assertEqual(rc, 1)
        self.assertIn("chapter", buf.getvalue())
        self.assertNotIn("Traceback", buf.getvalue())

    def test_valid_json_still_works(self):
        p = os.path.join(self.td, "ok.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump([{"chapter": 1, "title": "试", "factors": ["core_character"]}], fh)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = conf.run_json(p, 1)
        self.assertEqual(rc, 0)
        self.assertIn("冲突值 = 3", buf.getvalue())


# ─────────────────────────── cover_check：截断/零尺寸/假图 ───────────────────────────

class TestCoverCheck(TempCase):
    def _write(self, data):
        p = os.path.join(self.td, "封面.png")
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def test_valid_png_size(self):
        p = self._write(make_png(600, 800))
        self.assertEqual(cover.read_size(p), (600, 800))

    def test_truncated_png_rejected(self):
        p = self._write(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR\x00\x00")
        with self.assertRaises(ValueError):
            cover.read_size(p)
        r = run_tool("cover_check.py", p, "--platform", "custom", "--expect", "600x800")
        self.assertEqual(r.returncode, 2)
        self.assertIn("无法解析", r.stdout)

    def test_zero_height_rejected(self):
        def chunk(typ, data):
            return (struct.pack(">I", len(data)) + typ + data
                    + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
        bad = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 600, 0, 8, 2, 0, 0, 0)))
        p = self._write(bad + b"\x00" * 31000)
        with self.assertRaises(ValueError):
            cover.read_size(p)

    def test_zero_filled_fake_rejected(self):
        fake = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", 600, 800) + b"\x08\x00\x00\x00\x00" + b"\x00" * 31000)
        p = self._write(fake)
        with self.assertRaises(ValueError):
            cover.read_size(p)


# ─────────────────────────── check_refs：根目录校验 ───────────────────────────

class TestCheckRefs(TempCase):
    def test_missing_root_exit_2(self):
        self.assertEqual(refs.check(os.path.join(self.td, "不存在")), 2)

    def test_file_as_root_exit_2(self):
        p = os.path.join(self.td, "普通文件.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("正文")
        self.assertEqual(refs.check(p), 2)


# ─────────────────────────── grep_consistency：D 类告警去重 ───────────────────────────

TOC_MD = """# 章节目录

| 章号 | 标题 | 字数 | 节奏类型 | 校验结果 | 完成日期 |
|------|------|------|----------|----------|----------|
| 1 | 甲 | 100 | 主线 | 合格 | 2026-09-22 |
| 2 | 乙 | 100 | 主线 | 合格 | 2026-09-22 |
| 3 | 丙 | 100 | 主线 | 合格 | 2026-09-22 |

当前进度：已完成至第3章，下一章为第4章
"""
SNAP_MD = "## 张三\n- 状态：健康\n- 最后出场：第3章\n- 持有：无\n"


class TestGrepConsistency(TempCase):
    def _project(self, with_snapshot):
        p = Path(self.td) / "书"
        (p / "书稿").mkdir(parents=True)
        (p / "mind").mkdir()
        (p / "mind" / "章节目录.md").write_text(TOC_MD, encoding="utf-8")
        for n, t in ((1, "甲"), (2, "乙"), (3, "丙")):
            (p / "书稿" / f"第{n:03d}章_{t}.md").write_text(
                f"第{n}章 {t}\n\n" + base_chapter_text()[:400], encoding="utf-8")
        if with_snapshot:
            (p / "mind" / "角色状态快照.md").write_text(SNAP_MD, encoding="utf-8")
        return str(p)

    def test_d_warning_not_duplicated_with_snapshot(self):
        issues = grep.scan(self._project(True))
        d_issues = [i for i in issues if i[0] == "D"]
        self.assertEqual(len(d_issues), 1, d_issues)

    def test_d_warning_without_snapshot(self):
        issues = grep.scan(self._project(False))
        self.assertEqual(len([i for i in issues if i[0] == "D"]), 1)


# ─────────────────────────── gen_index：进度行待办保留 ───────────────────────────

class TestGenIndex(TempCase):
    def test_progress_todo_preserved(self):
        p = Path(self.td) / "书"
        (p / "书稿").mkdir(parents=True)
        (p / "mind").mkdir()
        for n, t in ((1, "甲"), (2, "乙"), (3, "丙")):
            (p / "书稿" / f"第{n:03d}章_{t}.md").write_text(
                f"第{n}章 {t}\n\n林舟推门进去，把灯关上，然后坐在桌边等消息传回来。", encoding="utf-8")
        (p / "mind" / "章节目录.md").write_text(TOC_MD.replace(
            "当前进度：已完成至第3章，下一章为第4章",
            "当前进度：已完成至第3章，下一章为第4章；待办：修复伏笔F001"), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gen.build(str(p))
        self.assertEqual(rc, 0)
        out = (p / "mind" / "章节目录.md").read_text(encoding="utf-8")
        self.assertIn("已完成至第3章，下一章为第4章", out)
        self.assertIn("待办：修复伏笔F001", out)


# ─────────────────────────── visualize：决策表/节奏/占位符/失败轮 ───────────────────────────

class TestVisualize(TempCase):
    def test_scan_decisions_two_column_table(self):
        mind = Path(self.td) / "mind"
        mind.mkdir()
        (mind / "剧情走向锁定.md").write_text(
            "| 日期 | 决策 |\n|---|---|\n| 2026-09-22 | 留下铜锁 |\n", encoding="utf-8")
        rows = vis.scan_decisions(str(mind))
        self.assertEqual(rows, [{"date": "2026-09-22", "decision": "留下铜锁", "source": ""}])

    def test_rhythm_warnings_use_real_numbers(self):
        sparse = [{"no": 1, "type": "主线"}, {"no": 2, "type": "主线"}, {"no": 10, "type": "主线"}]
        self.assertEqual(vis.rhythm_warnings(sparse), [])
        run3 = [{"no": n, "type": "主线"} for n in (4, 5, 6)]
        self.assertEqual(vis.rhythm_warnings(run3), ["第4-6章连续 3 章「主线」"])
        mixed = [{"no": n, "type": t} for n, t in
                 ((1, "缓冲-对话"), (2, "缓冲-事件"), (3, "缓冲-对话"), (4, "缓冲-事件"))]
        self.assertEqual(vis.rhythm_warnings(mixed), ["第1-4章连续缓冲章合计 4 章"])

    def test_apply_template_single_pass(self):
        html = "X__DATA__Y__TITLE__Z"
        data = r'{"t":"A__TITLE__B\C"}'
        out = vis.apply_template(html, data, "书名", "v7.25")
        self.assertEqual(out, r'X{"t":"A__TITLE__B\C"}Y书名Z')
        self.assertEqual(out.count("__TITLE__"), 1)

    def test_scan_scores_failure_round_clears_old_score(self):
        mind = Path(self.td) / "mind"
        mind.mkdir()
        (mind / "朱雀检测报告.md").write_text(
            "| 章号 | 标题 | AI% | 疑似% | 人类分 | 较上轮 | 结论 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 1 | 甲 | 5.0 | 3.0 | 92.0 | - | 通过 |\n"
            "\n第二轮\n\n"
            "| 章号 | 标题 | AI% | 疑似% | 人类分 | 较上轮 | 结论 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 1 | 甲 | - | - | - | - | 检测失败 |\n", encoding="utf-8")
        scores = vis.scan_scores(str(mind))
        self.assertEqual(scores["朱雀"], {})

    def test_skill_version_reads_skill_md(self):
        self.assertRegex(vis.skill_version(), r"^v\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
