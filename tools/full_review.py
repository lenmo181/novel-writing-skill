# -*- coding: utf-8 -*-
"""全文审稿流水线（v7.39）：全书诊断 → P0-P3 分级 → 修复队列 → 二审对比。

职责单一（治理铁律）：**只诊断，不修改**——本工具永不改写正文/档案/大纲。
产物两件：mind/全文审稿报告.md（人读）+ mind/全文审稿队列.json（修复执行层消费，十字段）。
二审：再次运行时自动读取上一轮队列，输出「问题消失/保留/新增/回归」四分类对比节。
阈值真源：tools/config.py（FULL_REVIEW_* / WALL_*），常量表·十三与之一致，lint/测试守护。

问题分级（与《体检》P0-P3 统一口径）：
  P0 设定崩坏/时间线矛盾/章节顺序错误（必须先修）
  P1 明显影响追读（打圈、字数失控、节奏连续同型）
  P2 影响读感（AI味、重复套路、对话极端）
  P3 整洁性（档案滞后、目录日期缺失）
问题分类：单章 / 跨章 / 全书 / 设定 / 未知。

用法：
  python tools/full_review.py "<项目根>"            # 第一轮（或自动二审）
  python tools/full_review.py "<项目根>" --strict   # 存在 P0/P1 时退出码 1（发布门）
  python tools/full_review.py "<项目根>" --json     # JSON 输出（含二审对比）
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402  阈值延迟绑定（测试可运行时修改 config 验证传播）
from canonical_parser import parse_role_snapshot

DEAD_MARK_RE = re.compile(r"已?(_|\s|）)?(死亡|阵亡|身死|毙命|牺牲|陨落|已死|去世|离世)")
CH_NUM_RE = re.compile(r"第(\d{1,5})[章回节]")
RHYTHM_TYPE_RE = re.compile(r"(主线|峰值|缓冲-对话|缓冲-线索|缓冲-代价|校准)")

# 修复执行层映射（诊断器 → 专项修复器；full_review 自身永不执行修复）
REPAIR_MAP = {
    ("全书", "P0"): ("补写缺章或 gen_index.py 重排目录", "仅缺失章号的正文位", "不得重排已有正文章号"),
    ("设定", "P0"): ("continuity_check.py 定位 → 就地改写或档案修正", "该角色出场段 + mind/角色状态快照.md 对应行", "禁止静默删除出场（回忆/幻觉/替身须在快照标注）"),
    ("设定", "P1"): ("同上（P0 设定流程）", "同上", "同上"),
    ("跨章", "P1"): ("章纲层调整：缓冲章三型轮换 / 变量注入", "章纲 + 对应缓冲章", "不整章重写主线章"),
    ("单章", "P1"): ("润色扩写配方（太短）/ 删冗（超长）；功能章豁免并在目录注明", "该章正文", "不注水、不为达标强删剧情锚点"),
    ("跨章", "P2"): ("变量注入：换冲突对象/目标/信息/代价之一", "冲突变量层（非语言层）", "禁止只做语言润色（换皮重复润色无效）"),
    ("单章", "P2"): ("去AI味 8 Gate 定向改写 / 对话归位六式收敛；体裁例外走书格钉参数", "病灶段", "不强加无意义对话/修辞凑指标"),
    ("跨章", "P2"): ("缓冲-线索章推进，或显式降级/废弃并在追踪表登记", "推进章 + mind/伏笔追踪表.md", "不当章硬回收（信息解密≤30% 红线）"),
    ("全书", "P3"): ("卷末档案整理", "mind/", "不动正文"),
    ("单章", "P3"): ("按提示转码/补字段", "该文件", "不重写内容"),
}


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
        self.issues = []

    def add(self, level, cat, loc, msg, evidence=""):
        rec, scope, forbid = REPAIR_MAP.get((cat, level), REPAIR_MAP.get((cat, "P2"), ("人工裁定", "最小范围", "禁止整章重写")))
        self.issues.append({
            "level": level, "cat": cat, "loc": loc,
            "msg": msg, "evidence": evidence or msg,
            "recommended_action": rec, "repair_scope": scope, "forbidden_action": forbid,
        })

    # ── 阶段1a：结构（P0 章节断档/重复）──
    def scan_structure(self, chapters, unrecognized):
        nums = [n for n, _ in chapters]
        dups = sorted({n for n in nums if nums.count(n) > 1})
        if dups:
            self.add("P0", "全书", f"第{','.join(map(str, dups))}章",
                     f"章节号重复：{dups}", f"书稿/ 中第{dups}章存在多文件")
        gaps = []
        for a, b in zip(nums, nums[1:]):
            if b > a + 1:
                gaps.append(f"第{a + 1}章" if b == a + 2 else f"第{a + 1}-{b - 1}章")
        if gaps:
            self.add("P0", "全书", "；".join(gaps[:6]) + ("…" if len(gaps) > 6 else ""),
                     f"章节号断档 {len(gaps)} 处（缺章或编号跳号）", f"章号序列缺口：{gaps[:6]}")
        if unrecognized:
            self.add("P3", "全书", "书稿/",
                     f"{len(unrecognized)} 个文件无法识别章号：{unrecognized[:3]}…", str(unrecognized[:3]))

    # ── 阶段1b：档案层（P0 死亡复活 / P2 伏笔沉睡）──
    def scan_archive(self, chapters, cur_max):
        snap = self.root / "mind" / "角色状态快照.md"
        if snap.is_file():
            roles = parse_role_snapshot(snap)
            for name, fields in sorted(roles.items()):
                status = fields.get("状态", "") + fields.get("伤势", "")
                if not DEAD_MARK_RE.search(status):
                    continue
                last_m = re.search(r"第\s*(\d{1,6})\s*章", fields.get("最后出场", ""))
                last_ch = int(last_m.group(1)) if last_m else None
                aliases = [x.strip() for x in re.split(r"[、，,/;；]", fields.get("别名", "")) if x.strip() and x.strip() not in {"无", "暂无", "-"}]
                terms = [name] + aliases
                resurf = []
                for n, p in chapters:
                    if last_ch is not None and n <= last_ch:
                        continue
                    body = chapter_body(p)
                    if body and any(term in body for term in terms if term):
                        resurf.append(n)
                        if len(resurf) >= 3:
                            break
                if resurf:
                    level = "P0" if (last_ch is None or len(resurf) >= 2) else "P1"
                    self.add(level, "设定", f"{name}（快照标记已故）",
                             f"已亡角色在第{chr(44).join(map(str, resurf))}章再次出现姓名/别名",
                             "快照：状态=" + fields.get("状态", "") + "；最后出场=" + fields.get("最后出场", "未填写") + "；正文命中章节：" + str(resurf))
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
                    limit = {1: None, 2: config.FULL_REVIEW_FORESHADOW_T2, 3: config.FULL_REVIEW_FORESHADOW_T3}.get(tier)
                    if limit and last_push and cur_max - last_push > limit:
                        self.add("P2", "跨章", row[:30],
                                 f"T{tier} 伏笔疑似沉睡：最后推进第{last_push}章，当前第{cur_max}章（阈值{limit}）",
                                 f"追踪表行：{row[:60]}")

    # ── 阶段1c：章节级统计 ──
    def scan_chapters(self, chapters):
        stats = []
        prev = None
        for n, p in chapters:
            body = chapter_body(p)
            if body is None:
                self.add("P3", "单章", f"第{n}章", "文件编码无法解析", str(p))
                continue
            chars = count_cjk(body)
            span = sum(count_cjk(m) for m in re.findall("[“「][^”」]*[”」]", body))
            dpct = round(span * 100 / chars, 1) if chars else 0
            stats.append({"n": n, "chars": chars, "dpct": dpct, "body": body})
            if prev is not None:
                overlap = len(ngram_set(prev) & ngram_set(body))
                base = min(len(ngram_set(prev)), len(ngram_set(body))) or 1
                if overlap * 100 / base > config.FULL_REVIEW_NGRAM_OVERLAP_WARN:
                    self.add("P2", "跨章", f"第{n - 1}-{n}章",
                             f"相邻章 3-gram 重复率 {overlap * 100 // base}%（>{config.FULL_REVIEW_NGRAM_OVERLAP_WARN}%）疑似换皮重复",
                             f"重叠 3-gram {overlap}/{base}")
            prev = body
        if not stats:
            return stats
        lens = sorted(s["chars"] for s in stats)
        med = lens[len(lens) // 2] or 1
        for s in stats:
            if s["chars"] and med >= config.FULL_REVIEW_LENGTH_MIN_MEDIAN:
                if s["chars"] > med * config.FULL_REVIEW_LENGTH_TOP_RATIO:
                    self.add("P1", "单章", f"第{s['n']}章",
                             f"字数 {s['chars']} 显著偏离书内中位 {med}（>{config.FULL_REVIEW_LENGTH_TOP_RATIO}x）",
                             f"章字数 {s['chars']}；中位 {med}")
                elif s["chars"] > med * config.FULL_REVIEW_LENGTH_HIGH_RATIO or s["chars"] < med * config.FULL_REVIEW_LENGTH_LOW_RATIO:
                    self.add("P2", "单章", f"第{s['n']}章",
                             f"字数 {s['chars']} 偏离书内中位 {med}",
                             f"章字数 {s['chars']}；中位 {med}")
            if s["dpct"] > config.FULL_REVIEW_DIALOG_MAX:
                self.add("P2", "单章", f"第{s['n']}章", f"对话占比 {s['dpct']}% (>{config.FULL_REVIEW_DIALOG_MAX}%)",
                         f"span {s['dpct']}%")


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
            cells = [c.strip() for c in line.strip().split("|") if c.strip()]
            m_num = CH_NUM_RE.search(line)
            if not m_num and cells and cells[0].isdigit():
                m_num_value = int(cells[0])
            else:
                m_num_value = int(m_num.group(1)) if m_num else None
            m_typ = RHYTHM_TYPE_RE.search(line)
            if m_num_value is not None and m_typ:
                seq.append((m_num_value, m_typ.group(1)))
        seq.sort()
        if not seq:
            return

        same_run = []
        buffer_run = []
        for n, t in seq:
            if same_run and (n != same_run[-1][0] + 1 or t != same_run[-1][1]):
                self._same_rhythm_flush(same_run)
                same_run = []
            same_run.append((n, t))

            if t.startswith("缓冲"):
                if buffer_run and n != buffer_run[-1][0] + 1:
                    self._buffer_flush(buffer_run)
                    buffer_run = []
                buffer_run.append((n, t))
            else:
                self._buffer_flush(buffer_run)
                buffer_run = []
        self._same_rhythm_flush(same_run)
        self._buffer_flush(buffer_run)

    def _same_rhythm_flush(self, run):
        if len(run) < config.FULL_REVIEW_RHYTHM_SAME_STREAK or run[0][1].startswith("缓冲"):
            return
        t = run[0][1]
        n0, n1 = run[0][0], run[-1][0]
        self.add("P1", "跨章", f"第{n0}-{n1}章",
                 f"节奏类型「{t}」连续 {len(run)} 章（≥{config.FULL_REVIEW_RHYTHM_SAME_STREAK}）",
                 f"章节目录节奏列：{t}×{len(run)}")

    def _buffer_flush(self, run):
        if len(run) < config.FULL_REVIEW_RHYTHM_BUFFER_STREAK:
            return
        n0, n1 = run[0][0], run[-1][0]
        kinds = "、".join(t for _, t in run)
        self.add("P1", "跨章", f"第{n0}-{n1}章",
                 f"缓冲型节奏合计连续 {len(run)} 章（≥{config.FULL_REVIEW_RHYTHM_BUFFER_STREAK}）",
                 f"章节目录节奏列：{kinds}")

P_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CAT_ORDER = {"设定": 0, "全书": 1, "跨章": 2, "单章": 3, "未知": 4}


CONFIRMED_FIXED_STATUSES = {"fixed", "auto_fixed"}


def issue_key(it):
    return (it["cat"], it["loc"], it["msg"])


def build_queue(issues, round_no, prev_items=None):
    """生成修复队列十字段；沿用状态，但历史 fixed/auto_fixed 重新出现时自动 reopened。"""
    prev_status = {issue_key(p): p.get("status", "open") for p in (prev_items or [])}
    queue = []
    for i, it in enumerate(issues, 1):
        key = issue_key(it)
        status = prev_status.get(key, "open")
        if status in CONFIRMED_FIXED_STATUSES:
            status = "reopened"
        item = {"issue_id": f"FR-{round_no:02d}-{i:03d}", **it, "status": status}
        queue.append(item)
    return queue


def diff_rounds(prev_items, cur_queue, resolved_log=None):
    """二审对比：resolved/persisted/new/regressed 四分类。

    “回归”只针对曾明确登记为 fixed/auto_fixed 的历史问题；
    单纯因阈值、书格或检测条件变化而消失的问题，不进入回归记忆。
    """
    prev_keys = {issue_key(p) for p in prev_items}
    cur_keys = {issue_key(q) for q in cur_queue}
    fixed_locs = {(p["cat"], p["loc"]) for p in prev_items if p.get("status") in CONFIRMED_FIXED_STATUSES}
    for rec in (resolved_log or []):
        if rec.get("prev_status") in CONFIRMED_FIXED_STATUSES:
            fixed_locs.add((rec.get("cat"), rec.get("loc")))
    resolved = [p for p in prev_items if issue_key(p) not in cur_keys]
    persisted = [q for q in cur_queue if issue_key(q) in prev_keys]
    new_items = [q for q in cur_queue if issue_key(q) not in prev_keys]
    regressed = [q for q in new_items if (q["cat"], q["loc"]) in fixed_locs]
    return {
        "resolved": [{"cat": p["cat"], "loc": p["loc"], "msg": p["msg"], "prev_status": p.get("status", "open")} for p in resolved],
        "persisted": [{"issue_id": q["issue_id"], "loc": q["loc"], "msg": q["msg"]} for q in persisted],
        "new": [{"issue_id": q["issue_id"], "loc": q["loc"], "msg": q["msg"]} for q in new_items],
        "regressed": [{"issue_id": q["issue_id"], "loc": q["loc"], "msg": q["msg"]} for q in regressed],
    }


QUEUE_PATH = "mind/全文审稿队列.json"
REPORT_PATH = "mind/全文审稿报告.md"


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

    # 上一轮队列（存在则进入二审；resolved_log 为跨轮回归记忆）
    qpath = root / QUEUE_PATH
    prev_items, round_no, resolved_log = [], 1, []
    if qpath.is_file():
        try:
            prev = json.loads(qpath.read_text(encoding="utf-8"))
            prev_items = prev.get("issues") or []
            round_no = int(prev.get("round", 1)) + 1
            resolved_log = prev.get("resolved_log") or []
        except (ValueError, OSError):
            prev_items = []
    queue = build_queue(issues, round_no, prev_items)
    d = diff_rounds(prev_items, queue, resolved_log) if (prev_items or resolved_log) else None
    if d is not None:
        confirmed_resolved = [r for r in d["resolved"] if r.get("prev_status") in CONFIRMED_FIXED_STATUSES]
        resolved_log = resolved_log + confirmed_resolved[-200:]  # 仅保存明确修复项

    counts = {lv: sum(1 for q in queue if q["level"] == lv) for lv in ("P0", "P1", "P2", "P3")}
    queue_doc = {
        "version": config.SKILL_VERSION, "round": round_no, "n_chapters": len(chapters),
        "to_chapter": cur_max, "counts": counts, "issues": queue, "resolved_log": resolved_log,
    }
    try:
        qpath.parent.mkdir(parents=True, exist_ok=True)
        qpath.write_text(json.dumps(queue_doc, ensure_ascii=False, indent=1), encoding="utf-8")
        q_saved = str(qpath)
    except OSError as e:
        q_saved = f"队列落盘失败：{e}"

    lines = [
        "# 全文审稿报告（full_review.py）",
        "",
        f"- 版本：v{config.SKILL_VERSION}；项目：{root.name}；扫描章节：{len(chapters)}（至第{cur_max}章）；轮次：第 {round_no} 轮",
        f"- 结论：P0×{counts['P0']} P1×{counts['P1']} P2×{counts['P2']} P3×{counts['P3']}",
        "- 分级：P0 设定崩坏/顺序错误｜P1 影响追读｜P2 影响读感｜P3 整洁性；类别：设定/全书/跨章/单章",
        "- 本工具只诊断不修复；修复按 mind/全文审稿队列.json 逐条执行（十字段：issue_id/level/cat/loc/msg/evidence/recommended_action/repair_scope/forbidden_action/status），修后重跑本工具出二审对比",
        "",
        "| issue_id | 级别 | 类别 | 位置 | 问题 | 建议动作 | 修复范围 | 禁止动作 | 状态 |",
        "|---|------|------|------|------|---------|---------|---------|------|",
    ]
    for q in queue:
        lines.append(f"| {q['issue_id']} | {q['level']} | {q['cat']} | {q['loc']} | {q['msg']} | {q['recommended_action']} | {q['repair_scope']} | {q['forbidden_action']} | {q['status']} |")
    if d is not None:
        lines += [
            "",
            f"## 二审对比（第 {round_no - 1} 轮 → 第 {round_no} 轮）",
            "",
            f"- 问题消失：{len(d['resolved'])} 项（其中登记已修复：{sum(1 for r in d['resolved'] if r['prev_status'] in CONFIRMED_FIXED_STATUSES)}）",
            f"- 问题保留：{len(d['persisted'])} 项",
            f"- 新增问题：{len(d['new'])} 项",
            f"- 回归问题：{len(d['regressed'])} 项（上轮已修复位置再次出问题——优先回查修复方式）",
        ]
        for tag, items in (("消失", d["resolved"]), ("保留", d["persisted"]), ("新增", d["new"]), ("回归", d["regressed"])):
            for it in items[:8]:
                lines.append(f"  - [{tag}] {it['loc']}｜{it['msg']}")
    report = "\n".join(lines) + "\n"
    rpath = root / REPORT_PATH
    try:
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_text(report, encoding="utf-8")
        r_saved = str(rpath)
    except OSError as e:
        r_saved = f"报告落盘失败：{e}"

    if as_json:
        print(json.dumps({**queue_doc, "round_diff": d, "queue": q_saved, "report": r_saved},
                         ensure_ascii=False, indent=1))
    else:
        print(f"[i] 全文审稿（v{config.SKILL_VERSION}）第 {round_no} 轮：{len(chapters)} 章，问题 {len(queue)} 项 "
              f"(P0={counts['P0']} P1={counts['P1']} P2={counts['P2']} P3={counts['P3']})")
        for q in queue[:40]:
            print(f"[{q['level']}][{q['cat']}] {q['loc']}｜{q['msg']}｜→ {q['recommended_action']}｜范围：{q['repair_scope']}")
        if len(queue) > 40:
            print(f"[i] 其余 {len(queue) - 40} 项见队列")
        if d is not None:
            print(f"[i] 二审对比：消失 {len(d['resolved'])}｜保留 {len(d['persisted'])}｜新增 {len(d['new'])}｜回归 {len(d['regressed'])}")
            for it in d["regressed"][:5]:
                print(f"[!] 回归：{it['loc']}｜{it['msg']}（该位置上轮已修复——回查修复方式）")
        print(f"[i] 队列：{q_saved}")
        print(f"[i] 报告：{r_saved}")
        if counts["P0"]:
            print("[!] 存在 P0：必须先修再续写（按队列逐项确认，禁止销毁式重写）")
    if strict and (counts["P0"] or counts["P1"]):
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="全文审稿流水线（只读诊断）：P0-P3 分级 + 修复队列 + 二审对比")
    ap.add_argument("project", help="小说项目根目录")
    ap.add_argument("--strict", action="store_true", help="存在 P0/P1 时退出码 1（发布门）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()
    sys.exit(run_review(Path(args.project).expanduser(), strict=args.strict, as_json=args.json))


if __name__ == "__main__":
    main()
