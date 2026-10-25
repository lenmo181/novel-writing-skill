# -*- coding: utf-8 -*-
"""事实台账（Fact Ledger，v7.49）——先登记后写、到期必兑、数字事实优先登记。

对标三个开源项目的能力交集：
  * chinese-novelist-skill「设定与事实词典」：先登记后写；到期必兑；数字事实优先登记。
  * AI_NovelGenerator `entity_state_history`：实体状态随章推进的历史留痕。
  * MuMuAINovel 向量库之外的「确定性状态层」思路。

与既有 mind/ 七档案的关系
------------------------
本台账**不是第八个 mind 档案**，而是给七档案里的「事实」补一层可核验的登记簿：
  · 角色状态快照（mind/角色状态快照.md）记「现在是什么样」；
  · 事实台账记「哪些事是真的、什么时候成立、欠着什么时候还」。
两者互补：快照层保证不穿帮，台账层保证因果链不断、数字不打架。

台账文件：mind/事实台账.md（Markdown 表格，纯文本，可手写也可脚本写入）

表格格式
--------
| 编号 | 事实 | 类型 | 位置 | 未知原因 | 登记章 | 到期章 | 状态 | 依据 |

列语义：
  编号     FL-001 起，建议与伏笔编号（F-xxx）区分开，避免同号两义
  事实     一句话，必须可判定真假（不可写「气氛紧张」这类不可核验句）
  类型     数字 / 设定 / 状态 / 关系 / 物品 / 地理 / 时间
  位置     book_start / volume_start / chapter_before / chapter_after / unknown
           可带参数：chapter_before:12（须在第12章前成立）、volume_start:3（第3卷起）、
           unknown:needs_review（位置未知，原因写在参数或「未知原因」列）
  未知原因 position=unknown 时必填，取值见 config.FACT_LEDGER_UNKNOWN_REASONS
  登记章   首次登记章号（先登记后写的锚点）
  到期章   承诺兑现的章号；到期未兑现 = 到期必兑违规
  状态     已登记 / 已兑现 / 待回收 / 已作废 / 不适用
  依据     指向正文位置或来源（章节号 / 设定文件 / 考据条目）

只读检查项
----------
  FACT_ID_DUP          编号重复
  FACT_TYPE_UNKNOWN    类型不在白名单
  FACT_POSITION_BAD    位置语义不在白名单
  FACT_UNKNOWN_REASON  position=unknown 但未填合法原因
  FACT_REASON_STALE    position≠unknown 却填了原因
  FACT_STATUS_BAD      状态不在白名单
  FACT_CHAPTER_BAD     登记章/到期章非正整数或到期章早于登记章
  FACT_DUE_UNPAID      到期必兑：当前最新章已过到期章，状态仍为「待回收」
  FACT_DIGIT_UNREGISTERED  数字事实优先登记：正文出现未登记的数字事实

写入边界
--------
本工具**只读**。它只报告「哪些事实没登记、哪些到期没兑现」，不替作者决定剧情，
不改写正文，不自动补全事实。写入由作者或 AI 按协议改 mind/事实台账.md。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import (FACT_LEDGER_DIGIT_MIN_LEN, FACT_LEDGER_DUE_OFFSET,
                    FACT_LEDGER_MAX_PER_CHAPTER, FACT_LEDGER_POSITIONS,
                    FACT_LEDGER_STATUSES, FACT_LEDGER_UNKNOWN_REASONS,
                    SKILL_VERSION)
from canonical_parser import chapter_body, chapter_files, read_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


LEDGER_REL = ("mind", "事实台账.md")

FACT_TYPES = ("数字", "设定", "状态", "关系", "物品", "地理", "时间")

# 事实表头识别：至少含「编号」与「事实」两列
HEADER_MIN_COLS = 2
CHAPTER_NUM_RE = re.compile(r"第\s*0*(\d{1,6})\s*章")
# 位置语义：book_start / volume_start / chapter_before / chapter_after / unknown，
# 其中后三类可带章号参数（chapter_before:12 / volume_start:3 / unknown:原因码）
POSITION_COL_RE = re.compile(
    r"^(book_start|volume_start|chapter_before|chapter_after|unknown)"
    r"(?::([A-Za-z_]+|\d{1,6}))?$"
)
# 中文数字 + 阿拉伯数字混合的数字事实候选（长度 ≥ FACT_LEDGER_DIGIT_MIN_LEN）
DIGIT_RUN_RE = re.compile(r"[0-9]{%d,}|[零一二三四五六七八九十百千万两]{%d,}"
                          % (FACT_LEDGER_DIGIT_MIN_LEN, FACT_LEDGER_DIGIT_MIN_LEN))
# 量词：数字 + 量词 = 强数字事实信号（"三百两"、"12枚"、"三天"）
UNIT_NUM_RE = re.compile(
    r"[0-9零一二三四五六七八九十百千万两]{1,8}\s*"
    r"(?:两|个|枚|颗|把|条|只|头|匹|件|年|岁|天|日|月|章|层|重|道|块|片|根|株|支|盏|碗|杯|里|丈|尺|斤|两|钱|贯|枚|%|％)"
)

COLUMNS = ("编号", "事实", "类型", "位置", "未知原因", "登记章", "到期章", "状态", "依据")


def add_issue(issues: list, level: str, code: str, location: str, message: str) -> None:
    issues.append({"level": level, "code": code, "location": location, "message": message})


def ledger_path(root: Path) -> Path:
    return root.joinpath(*LEDGER_REL)


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(set(c) <= {"-", ":", " ", "—"} for c in cells)


def parse_ledger(root: Path) -> tuple[list[dict], list[str]]:
    """解析事实台账。返回 (记录列表, 表头列名列表)。

    兼容两种写法：
      1) 带表头的标准表（首行含「编号」与「事实」）——按表头名定位列；
      2) 无表头的裸表——按 COLUMNS 固定顺序定位。
    """
    path = ledger_path(root)
    if not path.is_file():
        return [], []
    rows: list[dict] = []
    header: list[str] = []
    for lineno, raw in enumerate(read_text(path).splitlines(), 1):
        line = raw.strip()
        if not line or not line.startswith("|"):
            continue
        cells = split_row(line)
        if is_separator(cells):
            continue
        if not header and "编号" in cells and "事实" in cells:
            header = cells
            continue
        if len(cells) < HEADER_MIN_COLS:
            continue
        # 表头不足时用固定列序补齐（允许只写前 N 列）
        names = header if header and len(header) >= len(cells) else list(COLUMNS[:len(cells)])
        record = {"_line": lineno}
        for idx, name in enumerate(names):
            record[name] = cells[idx] if idx < len(cells) else ""
        if not record.get("编号") and not record.get("事实"):
            continue
        rows.append(record)
    return rows, header


def cell(record: dict, name: str) -> str:
    return (record.get(name) or "").strip()


def parse_chapter_number(value: str) -> int | None:
    m = CHAPTER_NUM_RE.search(value or "")
    return int(m.group(1)) if m else None


def check_structure(rows: list[dict], issues: list) -> None:
    """结构层校验：编号唯一性、枚举合法性、章节号合法性。"""
    seen: dict[str, int] = {}
    for record in rows:
        line = record["_line"]
        loc = f"mind/事实台账.md:{line}"
        fid = cell(record, "编号")
        fact = cell(record, "事实")
        if not fid and not fact:
            continue
        if not fid:
            add_issue(issues, "medium", "FACT_ID_MISSING", loc, "事实行缺编号")
        elif fid in seen:
            add_issue(issues, "medium", "FACT_ID_DUP", loc,
                      f"事实编号「{fid}」重复（首次出现在第{seen[fid]}行）")
        else:
            seen[fid] = line
        if not fact:
            add_issue(issues, "medium", "FACT_TEXT_MISSING", loc,
                      f"事实「{fid}」缺事实描述——台账只登记可判定真假的事")

        ftype = cell(record, "类型")
        if ftype and ftype not in FACT_TYPES:
            add_issue(issues, "low", "FACT_TYPE_UNKNOWN", loc,
                      f"事实「{fid}」类型「{ftype}」不在白名单（{'/'.join(FACT_TYPES)}）")

        position = cell(record, "位置")
        reason = cell(record, "未知原因")
        pos_match = POSITION_COL_RE.match(position) if position else None
        if position and not pos_match:
            add_issue(issues, "low", "FACT_POSITION_BAD", loc,
                      f"事实「{fid}」位置「{position}」不在白名单"
                      f"（{'/'.join(FACT_LEDGER_POSITIONS)}，可带参数如 chapter_before:12）")
        elif pos_match:
            base, param = pos_match.group(1), pos_match.group(2)
            if base == "unknown":
                # unknown 的参数就是未知原因，写法为 unknown:<reason>
                inline_reason = param or ""
                if not inline_reason and not reason:
                    add_issue(issues, "medium", "FACT_UNKNOWN_REASON", loc,
                              f"事实「{fid}」位置为 unknown 但未填未知原因")
                elif inline_reason and inline_reason not in FACT_LEDGER_UNKNOWN_REASONS:
                    add_issue(issues, "low", "FACT_UNKNOWN_REASON", loc,
                              f"事实「{fid}」未知原因「{inline_reason}」不在枚举内"
                              f"（{'/'.join(FACT_LEDGER_UNKNOWN_REASONS)}）")
                elif reason and reason not in FACT_LEDGER_UNKNOWN_REASONS:
                    add_issue(issues, "low", "FACT_UNKNOWN_REASON", loc,
                              f"事实「{fid}」未知原因「{reason}」不在枚举内"
                              f"（{'/'.join(FACT_LEDGER_UNKNOWN_REASONS)}）")
            else:
                # chapter_before / chapter_after 需要章号参数（体积：卷号或章号）
                if base in ("chapter_before", "chapter_after") and not param:
                    add_issue(issues, "medium", "FACT_POSITION_BAD", loc,
                              f"事实「{fid}」位置「{position}」缺少章号参数"
                              f"（应写作 {base}:章号）")
                if reason:
                    add_issue(issues, "low", "FACT_REASON_STALE", loc,
                              f"事实「{fid}」位置为 {position} 却填了未知原因")

        status = cell(record, "状态")
        if status and status not in FACT_LEDGER_STATUSES:
            add_issue(issues, "low", "FACT_STATUS_BAD", loc,
                      f"事实「{fid}」状态「{status}」不在白名单"
                      f"（{'/'.join(FACT_LEDGER_STATUSES)}）")

        reg = parse_chapter_number(cell(record, "登记章"))
        due = parse_chapter_number(cell(record, "到期章"))
        if cell(record, "登记章") and reg is None:
            add_issue(issues, "low", "FACT_CHAPTER_BAD", loc,
                      f"事实「{fid}」登记章「{cell(record, '登记章')}」不是合法章号")
        if cell(record, "到期章") and due is None:
            add_issue(issues, "low", "FACT_CHAPTER_BAD", loc,
                      f"事实「{fid}」到期章「{cell(record, '到期章')}」不是合法章号")
        if reg is not None and due is not None and due < reg:
            add_issue(issues, "medium", "FACT_CHAPTER_BAD", loc,
                      f"事实「{fid}」到期章（第{due}章）早于登记章（第{reg}章）")


def check_due(rows: list[dict], issues: list, latest_chapter: int) -> None:
    """到期必兑：已过到期章但状态仍为「待回收」= 承诺没兑现。"""
    if latest_chapter <= 0:
        return
    for record in rows:
        fid = cell(record, "编号")
        status = cell(record, "状态")
        due = parse_chapter_number(cell(record, "到期章"))
        if due is None or status != "待回收":
            continue
        if latest_chapter >= due:
            add_issue(issues, "medium", "FACT_DUE_UNPAID",
                      f"mind/事实台账.md:{record['_line']}",
                      f"事实「{fid}」承诺第{due}章兑现，当前已到第{latest_chapter}章仍未兑现"
                      f"——本章内兑现，或改状态/改到期章（改期要留依据）")


def collect_digit_candidates(text: str) -> set[str]:
    """抽取正文里的数字事实候选（数字串 + 数字+量词）。"""
    found = set()
    for m in UNIT_NUM_RE.finditer(text):
        token = re.sub(r"\s+", "", m.group(0))
        if len(token) >= FACT_LEDGER_DIGIT_MIN_LEN:
            found.add(token)
    for m in DIGIT_RUN_RE.finditer(text):
        found.add(m.group(0))
    return found


def check_digit_facts(rows: list[dict], issues: list, root: Path,
                      latest_chapter: int) -> dict:
    """数字事实优先登记：正文里出现的数字事实，台账里查不到就提示登记。

    口径刻意保守——只统计「数字+量词」这类强数字信号（如「三百两」「12枚」），
    纯数字串（如年份、门牌号）不单独计入，避免噪声淹没真问题。
    """
    ledger_digits = set()
    for record in rows:
        text_blob = " ".join(cell(record, key) for key in ("事实", "依据"))
        for token in collect_digit_candidates(text_blob):
            ledger_digits.add(token)
        if cell(record, "类型") == "数字":
            for token in DIGIT_RUN_RE.findall(text_blob):
                ledger_digits.add(token)

    # 计数按章节隔离：常量名是 MAX_PER_CHAPTER，跨章累计会把每章少量
    # 合法重复误报为超线，也会让长篇更容易被误杀。
    unregistered: dict[str, int] = {}
    unregistered_by_chapter: dict[str, dict[int, int]] = {}
    for number, path in chapter_files(root):
        if latest_chapter and number > latest_chapter:
            continue
        body = chapter_body(path)
        if not body:
            continue
        for m in UNIT_NUM_RE.finditer(body):
            token = re.sub(r"\s+", "", m.group(0))
            if len(token) < FACT_LEDGER_DIGIT_MIN_LEN:
                continue
            if token in ledger_digits:
                continue
            unregistered[token] = unregistered.get(token, 0) + 1
            by_chapter = unregistered_by_chapter.setdefault(token, {})
            by_chapter[number] = by_chapter.get(number, 0) + 1

    flagged: dict[str, int] = {}
    for token, count in sorted(unregistered.items(), key=lambda kv: (-kv[1], kv[0])):
        peak = max(unregistered_by_chapter.get(token, {}).values(), default=0)
        if peak < FACT_LEDGER_MAX_PER_CHAPTER:
            continue
        flagged[token] = peak
        add_issue(issues, "low", "FACT_DIGIT_UNREGISTERED", "mind/事实台账.md",
                  f"数字事实「{token}」单章最高出现 {peak} 次（全书 {count} 次）但台账未登记——"
                  f"数字类事实优先登记（先登记后写），否则前后章必打架")
    return {"unregistered_digit_facts": dict(sorted(unregistered.items())),
            "unregistered_digit_fact_peak_per_chapter": dict(sorted(flagged.items()))}


def check(root: Path) -> dict:
    root = Path(root)
    issues: list = []
    rows, header = parse_ledger(root)
    chapters = chapter_files(root)
    latest_chapter = max((num for num, _ in chapters), default=0)

    if not ledger_path(root).is_file():
        add_issue(issues, "low", "FACT_LEDGER_MISSING", "mind/事实台账.md",
                  "尚无事实台账（v7.49）：建议登记「数字/设定/状态」类事实并写明到期章，"
                  "供到期必兑与先登记后写核验")
        stats = {"row_count": 0, "latest_chapter": latest_chapter,
                 "unregistered_digit_facts": {},
                 "unregistered_digit_fact_peak_per_chapter": {}}
        return {"version": SKILL_VERSION, "root": str(root),
                "ok": not any(i["level"] == "high" for i in issues),
                "stats": stats, "issues": issues}

    check_structure(rows, issues)
    check_due(rows, issues, latest_chapter)
    digit_stats = check_digit_facts(rows, issues, root, latest_chapter)

    stats = {
        "row_count": len(rows),
        "latest_chapter": latest_chapter,
        "header_detected": bool(header),
    }
    stats.update(digit_stats)
    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "ok": not any(item["level"] == "high" for item in issues),
        "stats": stats,
        "issues": issues,
    }


def render(report: dict) -> str:
    issues = report.get("issues", [])
    stats = report.get("stats", {})
    lines = [
        f"# 事实台账检查（v{report['version']}）",
        "",
        f"- 项目根：`{report['root']}`",
        f"- 台账条目：{stats.get('row_count', 0)}；当前最新章：{stats.get('latest_chapter', 0)}",
        f"- 问题数：{len(issues)}",
        "",
        "| 级别 | 编号 | 位置 | 问题 |",
        "|---|---|---|---|",
    ]
    if issues:
        for item in issues:
            lines.append(f"| {item['level']} | {item['code']} | `{item['location']}` | {item['message']} |")
    else:
        lines.append("| - | - | - | 未发现事实台账问题 |")
    lines.extend([
        "",
        "本工具只读：不替作者决定事实是否成立，不改写正文，不自动补全台账。",
        "数字事实优先登记：正文出现的数字（数字+量词）应先入台账，再在正文落地。",
    ])
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=f"事实台账检查（先登记后写 / 到期必兑 / 数字事实优先登记）v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="将报告写入指定文件")
    parser.add_argument("--strict", action="store_true", help="发现任意问题时退出码为1")
    args = parser.parse_args(argv)

    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"[✗] 项目根不存在或不是目录：{root}")
        return 2
    report = check(root)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"报告已写入：{target}")
    else:
        print(output, end="")
    if args.strict and report["issues"]:
        return 1
    return 1 if any(item["level"] == "high" for item in report["issues"]) else 0


if __name__ == "__main__":
    sys.exit(main())
