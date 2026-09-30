# -*- coding: utf-8 -*-
"""全文审稿流水线（v7.33）：全书多维度诊断 → P0-P3 分级 → 修复队列。

只读工具：不修改任何文件；报告落盘 mind/全文审稿报告.md。

问题统一分级（与《体检》P0-P3 口径一致）：
  P0 设定崩坏/时间线矛盾/章节顺序错误（必须先修）
  P1 明显影响追读（打圈、字数失控、节奏连续同型）
  P2 影响读感（AI味、重复套路、对话极端）
  P3 整洁性（档案滞后、目录日期缺失）

问题统一分类：单章 / 跨章 / 全书 / 设定 / 未知。

用法：
  python tools/full_review.py "<项目根>"            # 全书流水线
  python tools/full_review.py "<项目根>" --strict   # 存在 P0/P1 时退出码 1（可接入发布门）
  python tools/full_review.py "<项目根>" --json     # JSON 输出
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SKILL_VERSION  # noqa: E402

DEAD_MARK_RE = re.compile(r"已?(_|\s|）)?(死亡|阵亡|身死|毙命|牺牲|陨落|已死|去世|离世)")
CH_NUM_RE = re.compile(r"第(\d{1,5})[章回节]")
RHYTHM_TYPE_RE = re.compile(r"(主线|峰值|缓冲-对话|缓冲-线索|缓冲-代价|校准)")


def read_text(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc), enc
        except (UnicodeDecodeError, OSError):
            continue
    return None, None


def find_chapters(root):
    """返回按章号排序的 [(章号, Path)]；识别不到章号的文件跳过并单独上报。"""
    book_dir = root / "书稿"
    base = book_dir if book_dir.is_dir() else root
    chapters, unrecognized = [], []
    for p in sorted(base.glob("*.md")):
        m = CH_NUM_RE.search(p.stem)
        if m:
            chapters.append((int(m.group(1)), p))
        elif p.name not in ("正文.md",):
            unrecognized.append(p.name)
    chapters.sort(key=lambda x: x[0])
    return chapters, unrecognized


def chapter_body(path):
    text, _ = read_text(path)
    if text is None:
        return None
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith(("#", ">", "---", "|"))]
    # 剥首个章节标题行
    if lines and CH_NUM_RE.match(lines[0]):
        lines = lines[1:]
    return "\n".join(lines)


def count_cjk(s):
    return len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef“”‘’]", s))


def ngram_set(text, n=3):
    clean = re.sub(r"\s+", "", text)
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


class Review:
    def __init__(self, root):
        self.root = root
        self.issues = []  # {level, cat, loc, msg, action}

    def add(self, level, cat, loc, msg, action):
        self.issues.append({
            "level": level, "cat": cat, "loc": loc,
            "msg": msg, "action": action,
        })

    # ── 阶段1a：结构（P0 章节断档/重复）──
    def scan_structure(self, chapters, unrecognized):
        nums = [n for n, _ in chapters]
        dups = sorted({n for n in nums if nums.count(n) > 1})
        if dups:
            self.add("P0", "全书", f"第{','.join(map(str, dups))}章",
                     f"章节号重复：{dups}",
                     "核对同名章节，合并或改号（project_audit.py 可复核）")
        gaps = []
        for a, b in zip(nums, nums[1:]):
            if b > a + 1:
                gaps.append(f"第{a + 1}章" if b == a + 2 else f"第{a + 1}-{b - 1}章")
        if gaps:
            self.add("P0", "全书", "；".join(gaps[:6]) + ("…" if len(gaps) > 6 else ""),
                     f"章节号断档 {len(gaps)} 处（缺章或编号跳号）",
                     "确认是否缺文件；缺章补写或重排目录（gen_index.py 重建目录）")
        if unrecognized:
            self.add("P3", "全书", "书稿/",
                     f"{len(unrecognized)} 个文件无法识别章号：{unrecognized[:3]}…",
                     "按「第XXX章_标题.md」规范重命名")

    # ── 阶段1b：档案层（P0 死亡复活 / P1 伏笔沉睡）──
    def scan_archive(self, chapters, cur_max):
        snap = self.root / "mind" / "角色状态快照.md"
        if snap.is_file():
            text, _ = read_text(snap)
            if text:
                for line in text.splitlines():
                    if "|" not in line:
                        continue
                    cells = [c.strip() for c in line.strip("|").split("|")]
                    row = "|".join(cells)
                    if not DEAD_MARK_RE.search(row):
                        continue
                    name = next((c for c in cells if 1 < len(c) <= 12 and not DEAD_MARK_RE.search(c)
                                 and not re.search(r"\d{2,}", c)), None)
                    if not name:
                        continue
                    last_m = re.search(r"(\d{1,5})", row)
                    last_ch = int(last_m.group(1)) if last_m else None
                    resurf = []
                    for n, p in chapters:
                        if last_ch and n <= last_ch:
                            continue
                        body = chapter_body(p)
                        if body and name in body:
                            resurf.append(n)
                            if len(resurf) >= 3:
                                break
                    if resurf:
                        lvl = "P0" if not last_ch else ("P0" if len(resurf) >= 2 else "P1")
                        self.add(lvl, "设定", f"{name}（快照标记已故）",
                                 f"已亡角色在第{','.join(map(str, resurf))}章再次出现姓名",
                                 "若非回忆/幻觉/替身设定 → 就地改写；有意为之 → 快照行标注「回忆出场」")
        foreshadow = self.root / "mind" / "伏笔追踪表.md"
        if foreshadow.is_file() and cur_max:
            text, _ = read_text(foreshadow)
            if text:
                for line in text.splitlines():
                    if "|" not in line:
                        continue
                    row = "|".join(c.strip() for c in line.strip("|").split("|"))
                    if not re.search(r"(进行|埋设|未回收|活跃)", row):
                        continue
                    tier_m = re.search(r"T(ier)?[-\s]?([123])", row, re.I)
                    tier = int(tier_m.group(2)) if tier_m else 3
                    nums = [int(x) for x in re.findall(r"第(\d{1,5})[章回节]?", row)]
                    if not nums:  # 无「第N章」格式时回退到行内纯数字（剔除编号/Tier 字段）
                        stripped = re.sub(r"F\d{1,4}|T(ier)?[-\s]?[123]", "", row, flags=re.I)
                        nums = [int(x) for x in re.findall(r"(\d{1,5})", stripped)]
                    last_push = max((x for x in nums if x <= cur_max), default=None)
                    limit = {1: None, 2: 40, 3: 20}.get(tier)
                    if limit and last_push and cur_max - last_push > limit:
                        self.add("P2", "跨章", row[:30],
                                 f"T{tier} 伏笔疑似沉睡：最后推进第{last_push}章，当前第{cur_max}章（阈值{limit}）",
                                 "安排缓冲-线索章推进或显式降级/废弃（更新追踪表状态）")

    # ── 阶段1c：章节级统计（P1 字数失控 / P2 AI味 / 对话极端）──
    def scan_chapters(self, chapters, quote_pair=("“", "”")):
        stats = []
        prev = None
        for n, p in chapters:
            body = chapter_body(p)
            if body is None:
                self.add("P3", "单章", f"第{n}章", "文件编码无法解析", "转 UTF-8 后重审")
                continue
            chars = count_cjk(body)
            span = sum(count_cjk(m) for m in re.findall("[" + quote_pair[0] + "][^" + quote_pair[1] + "]*[" + quote_pair[1] + "]", body))
            dpct = round(span * 100 / chars, 1) if chars else 0
            stats.append({"n": n, "chars": chars, "dpct": dpct, "body": body})
            if prev is not None:
                overlap = len(ngram_set(prev) & ngram_set(body))
                base = min(len(ngram_set(prev)), len(ngram_set(body))) or 1
                if overlap * 100 / base > 40:
                    self.add("P2", "跨章", f"第{n - 1}-{n}章",
                             f"相邻章 3-gram 重复率 {overlap * 100 // base}%（>40%）疑似换皮重复",
                             "变量注入破圈：换冲突对象/目标/信息/代价之一（勿只改语言）")
            prev = body
        if not stats:
            return stats
        lens = sorted(s["chars"] for s in stats)
        med = lens[len(lens) // 2] or 1
        for s in stats:
            if s["chars"] and med >= 1500 and (s["chars"] > med * 1.6 or s["chars"] < med * 0.55):
                self.add("P1" if s["chars"] > med * 2 else "P2", "单章", f"第{s['n']}章",
                         f"字数 {s['chars']} 显著偏离书内中位 {med}",
                         "功能章（加更/加长）可豁免并注明；否则扩写或删冗")
            if s["dpct"] > 55:
                self.add("P2", "单章", f"第{s['n']}章", f"对话占比 {s['dpct']}% (>55%)",
                         "确认是否剧本体；小说体按对话归位六式收敛叙述")
        return stats

    # ── 阶段1d：节奏连续（读章节目录节奏类型列）──
    def scan_rhythm(self, root, stats):
        idx = root / "mind" / "章节目录.md"
        if not idx.is_file():
            return
        text, _ = read_text(idx)
        if not text:
            return
        seq = []
        for line in text.splitlines():
            if "|" not in line:
                continue
            m_num = CH_NUM_RE.search(line)
            m_typ = RHYTHM_TYPE_RE.search(line)
            if m_num and m_typ:
                seq.append((int(m_num.group(1)), m_typ.group(1)))
        seq.sort()
        run = []
        for n, t in seq:
            if run and run[-1][1] == t:
                run.append((n, t))
            else:
                self._rhythm_flush(run)
                run = [(n, t)]
        self._rhythm_flush(run)

    def _rhythm_flush(self, run):
        if len(run) < 3:
            return
        t = run[0][1]
        n0, n1 = run[0][0], run[-1][0]
        if t.startswith("缓冲") and len(run) >= 4:
            self.add("P1", "跨章", f"第{n0}-{n1}章",
                     f"缓冲型节奏连续 {len(run)} 章（≥4）",
                     "插入主线/峰值章，或把其中一个缓冲章改为主线推进")
        elif not t.startswith("缓冲"):
            self.add("P1", "跨章", f"第{n0}-{n1}章",
                     f"节奏类型「{t}」连续 {len(run)} 章（≥3）",
                     "按缓冲章三型轮换（grep_consistency.py D 类同源）")


P_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CAT_ORDER = {"设定": 0, "全书": 1, "跨章": 2, "单章": 3, "未知": 4}


def run_review(root, strict=False, as_json=False):
    if not root.is_dir():
        print(f"[✗] 输入错误：项目根不存在 {root}")
        return 2
    chapters, unrecognized = find_chapters(root)
    if not chapters:
        print(f"[✗] 输入错误：{root} 下未发现章节文件（书稿/第XXX章_*.md）")
        return 2
    rv = Review(root)
    rv.scan_structure(chapters, unrecognized)
    cur_max = chapters[-1][0] if chapters else 0
    rv.scan_archive(chapters, cur_max)
    stats = rv.scan_chapters(chapters)
    rv.scan_rhythm(root, stats)
    issues = sorted(rv.issues, key=lambda i: (P_ORDER.get(i["level"], 9), CAT_ORDER.get(i["cat"], 9)))

    counts = {lv: sum(1 for i in issues if i["level"] == lv) for lv in ("P0", "P1", "P2", "P3")}
    report_path = root / "mind" / "全文审稿报告.md"
    lines = [
        "# 全文审稿报告（full_review.py）",
        "",
        f"- 版本：v{SKILL_VERSION}；项目：{root.name}；扫描章节：{len(chapters)}（至第{cur_max}章）",
        f"- 结论：P0×{counts['P0']} P1×{counts['P1']} P2×{counts['P2']} P3×{counts['P3']}",
        "- 分级：P0 设定崩坏/顺序错误｜P1 影响追读｜P2 影响读感｜P3 整洁性；类别：设定/全书/跨章/单章",
        "- 本工具只读；修复动作按队列逐项人工确认后执行，禁止销毁式重写",
        "",
        "| # | 级别 | 类别 | 位置 | 问题 | 建议动作 |",
        "|---|------|------|------|------|---------|",
    ]
    for i, it in enumerate(issues, 1):
        lines.append(f"| {i} | {it['level']} | {it['cat']} | {it['loc']} | {it['msg']} | {it['action']} |")
    report = "\n".join(lines) + "\n"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        saved = str(report_path)
    except OSError as e:
        saved = f"落盘失败：{e}"

    if as_json:
        print(json.dumps({"version": SKILL_VERSION, "n_chapters": len(chapters),
                          "counts": counts, "issues": issues, "report": saved},
                         ensure_ascii=False, indent=1))
    else:
        print(f"[i] 全文审稿（v{SKILL_VERSION}）：{len(chapters)} 章，问题 {len(issues)} 项 "
              f"(P0={counts['P0']} P1={counts['P1']} P2={counts['P2']} P3={counts['P3']})")
        for i, it in enumerate(issues[:40], 1):
            print(f"[{it['level']}][{it['cat']}] {it['loc']}｜{it['msg']}｜→ {it['action']}")
        if len(issues) > 40:
            print(f"[i] 其余 {len(issues) - 40} 项见报告")
        print(f"[i] 报告已落盘：{saved}")
        if counts["P0"]:
            print("[!] 存在 P0：必须先修再续写（就地修复，逐项确认）")
    if strict and (counts["P0"] or counts["P1"]):
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="全文审稿流水线（只读）：P0-P3 分级 + 修复队列")
    ap.add_argument("project", help="小说项目根目录")
    ap.add_argument("--strict", action="store_true", help="存在 P0/P1 时退出码 1（可接入发布门）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()
    sys.exit(run_review(Path(args.project).expanduser(), strict=args.strict, as_json=args.json))


if __name__ == "__main__":
    main()
