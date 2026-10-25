# -*- coding: utf-8 -*-
"""网络小说档案连续性检查（v7.34）。

聚焦“文件之间对不上”的机械问题：章节标题、时间线顺序、伏笔日期、
角色首末出场章和单章回顾覆盖率。语义冲突仍交给作者或审校流程裁定。

v7.49：补齐期待线悬空阈值常量（原引用点存在但未定义，触发 NameError 崩溃），
并接入伏笔到期/超期/近期待回收三层提醒（对标 MuMuAINovel）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import (EXPECTATION_STALE_CHAPTERS, FORESHADOW_DUE_OFFSET,
                    FORESHADOW_OVERDUE_OFFSET, FORESHADOW_STATUSES,
                    SKILL_VERSION)
from project_audit import chapter_files, add_issue

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


CHAPTER_NUM_RE = re.compile(r"第\s*0*(\d+)章")
DATE_ROW_RE = re.compile(r"^\s*\|?\s*第\s*0*(\d+)章\s*\|")
FIELD_RE = re.compile(r"^-\s*([^：:]+)[：:]\s*(.*?)\s*$")


def text(path):
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def chapter_numbers_in_text(path):
    return [int(match.group(1)) for match in CHAPTER_NUM_RE.finditer(text(path))]


def check_timeline(root, issues):
    path = root / "mind" / "时间线.md"
    if not path.is_file():
        return
    nums = []
    for line in text(path).splitlines():
        match = DATE_ROW_RE.search(line)
        if match:
            nums.append(int(match.group(1)))
    if nums != sorted(nums):
        add_issue(issues, "medium", "TIMELINE_REVERSE", "mind/时间线.md", "时间线章节顺序出现倒挂")
    duplicates = sorted(num for num in set(nums) if nums.count(num) > 1)
    if duplicates:
        add_issue(issues, "low", "TIMELINE_DUPLICATE", "mind/时间线.md", f"时间线重复记录章节：{duplicates}")


def check_roles(root, issues):
    path = root / "mind" / "角色状态快照.md"
    if not path.is_file():
        return
    current = None
    fields = {}
    def flush():
        if not current:
            return
        first = CHAPTER_NUM_RE.search(fields.get("首次出场章", ""))
        last = CHAPTER_NUM_RE.search(fields.get("最后出场", ""))
        if first and last and int(last.group(1)) < int(first.group(1)):
            add_issue(issues, "high", "ROLE_ORDER", "mind/角色状态快照.md",
                      f"角色“{current}”最后出场章早于首次出场章")
        if not last:
            add_issue(issues, "low", "ROLE_NO_LAST", "mind/角色状态快照.md",
                      f"角色“{current}”缺少最后出场字段")
    for line in text(path).splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            flush()
            current = heading.group(1).strip()
            fields = {}
            continue
        match = FIELD_RE.match(line.strip())
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()
    flush()


def check_foreshadows(root, issues, latest_chapter=0):
    """伏笔追踪表核验 + 到期三层提醒（v7.49）。

    表格格式（mind/伏笔追踪表.md）：
        | 编号 | 伏笔内容 | 埋设章 | 预计回收章 | Tier | 状态 |

    三层提醒（对标 MuMuAINovel 的「必须回收 / 已超期 / 近期待回收」）：
      · 必须回收：预计回收章 ≤ 当前最新章，状态仍未回收 → medium
      · 已超期：预计回收章 ≤ 当前最新章 - FORESHADOW_OVERDUE_OFFSET → high
      · 近期待回收：预计回收章 ≤ 当前最新章 + FORESHADOW_DUE_OFFSET → low
    """
    path = root / "mind" / "伏笔追踪表.md"
    if not path.is_file():
        return
    for index, line in enumerate(text(path).splitlines(), 1):
        if not line.strip().startswith("|") or re.match(r"^\s*\|?\s*-+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0] or not re.search(r"\d", cells[0]):
            continue
        planted = CHAPTER_NUM_RE.search(cells[2])
        planned = CHAPTER_NUM_RE.search(cells[3])
        if planted and planned and int(planned.group(1)) < int(planted.group(1)):
            add_issue(issues, "medium", "FORESHADOW_ORDER", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔“{cells[0]}”预计回收章早于埋设章")
        status = cells[5] if len(cells) >= 6 else ""
        if status and status not in FORESHADOW_STATUSES:
            add_issue(issues, "low", "FORESHADOW_STATUS", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔状态不在白名单：{status}")
        # ── v7.49 到期三层提醒 ──
        # 只对「未回收 / 部分回收」且已填了预计回收章的条目判定；
        # 已回收 / 已废弃 / 待定 不参与到期提醒（否则会对着已废弃伏笔催债）。
        if not planned or status in ("已回收", "已废弃", "待定", "-", ""):
            continue
        if status not in ("未回收", "部分回收"):
            continue
        due = int(planned.group(1))
        if latest_chapter <= 0:
            continue
        if due <= latest_chapter - FORESHADOW_OVERDUE_OFFSET:
            add_issue(issues, "high", "FORESHADOW_OVERDUE", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔“{cells[0]}”预计第{due}章回收，已超期 "
                      f"{latest_chapter - due} 章仍未回收——立即兑现或改期（改期要留理由）")
        elif due <= latest_chapter:
            add_issue(issues, "medium", "FORESHADOW_DUE", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔“{cells[0]}”预计第{due}章回收，已到期仍未回收——本章内兑现或显式改期")
        elif due <= latest_chapter + FORESHADOW_DUE_OFFSET:
            add_issue(issues, "low", "FORESHADOW_DUE_SOON", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔“{cells[0]}”预计第{due}章回收（当前第{latest_chapter}章）——"
                      f"提前准备，别忘了")


def check_toc_titles(root, chapters, issues):
    toc_path = root / "mind" / "章节目录.md"
    if not toc_path.is_file():
        return
    toc_titles = {}
    for line in text(toc_path).splitlines():
        if not line.lstrip().startswith("|") or re.match(r"^\s*\|?\s*-+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].isdigit():
            toc_titles[int(cells[0])] = cells[1]
    for row in chapters:
        if row["num"] not in toc_titles or not row["title"]:
            continue
        toc_title = re.sub(r"[*_`#]", "", toc_titles[row["num"]]).strip()
        if toc_title and toc_title != row["title"]:
            add_issue(issues, "low", "TOC_TITLE_MISMATCH", "mind/章节目录.md",
                      f"第{row['num']}章目录标题“{toc_title}”与文件名“{row['title']}”不一致")


def check_reviews(root, chapters, issues):
    review_dir = root / "mind" / "回顾"
    if not review_dir.is_dir():
        return
    existing = set()
    for path in review_dir.iterdir():
        match = re.match(r"^第0*(\d+)章回顾\.md$", path.name)
        if match:
            existing.add(int(match.group(1)))
    missing = sorted(set(row["num"] for row in chapters) - existing)
    if missing:
        add_issue(issues, "low", "REVIEW_MISSING", "mind/回顾/", f"缺少单章回顾：{missing[:20]}")


def check_expectations(root, chapters, issues):
    """期待线台账核验（v7.40）：活跃期待线跨章无推进 = 悬空，告警交语义复核。

    台账格式（mind/期待线.md，四型登记）：
    | 线名 | 类型 | 建立章 | 最近推进章 | 状态 |
    类型 ∈ 打脸预告/身份悬念/目标牵引/危机倒计时；状态 ∈ 活跃/已兑现/已放弃。
    """
    path = root / "mind" / "期待线.md"
    latest = max((row["num"] for row in chapters), default=0)
    if not path.is_file():
        if latest >= 5:
            add_issue(issues, "low", "EXPECTATION_NO_LEDGER", "mind/期待线.md",
                      "尚无期待线台账（v7.40）：第4章起建议登记四型期待线，供连续性核验")
        return
    valid_types = ("打脸预告", "身份悬念", "目标牵引", "危机倒计时")
    for index, line in enumerate(text(path).splitlines(), 1):
        if not line.strip().startswith("|") or re.match(r"^\s*\|?\s*-+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not cells[0] or cells[0] in ("线名", "---"):
            continue
        name, etype, status = cells[0], cells[1], cells[4]
        if etype and etype not in valid_types:
            add_issue(issues, "low", "EXPECTATION_TYPE", f"mind/期待线.md:{index}",
                      f"期待线「{name}」类型「{etype}」不在四型白名单")
        if status and status not in ("活跃", "已兑现", "已放弃", "-"):
            add_issue(issues, "low", "EXPECTATION_STATUS", f"mind/期待线.md:{index}",
                      f"期待线「{name}」状态「{status}」不在白名单（活跃/已兑现/已放弃）")
        if status != "活跃":
            continue
        pushed = CHAPTER_NUM_RE.search(cells[3])
        if not pushed:
            add_issue(issues, "low", "EXPECTATION_NO_PUSH", f"mind/期待线.md:{index}",
                      f"活跃期待线「{name}」缺最近推进章字段")
            continue
        gap = latest - int(pushed.group(1))
        if gap > EXPECTATION_STALE_CHAPTERS:
            add_issue(issues, "medium", "EXPECTATION_STALE", f"mind/期待线.md:{index}",
                      f"期待线「{name}」已 {gap} 章未推进（>{EXPECTATION_STALE_CHAPTERS} 章悬空）——"
                      f"推进、兑现或显式放弃，不许默默忘掉")


def check(root: Path):
    issues = []
    chapters = chapter_files(root)
    latest_chapter = max((row["num"] for row in chapters), default=0)
    check_timeline(root, issues)
    check_roles(root, issues)
    check_foreshadows(root, issues, latest_chapter)
    check_toc_titles(root, chapters, issues)
    check_reviews(root, chapters, issues)
    check_expectations(root, chapters, issues)
    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "chapter_count": len(chapters),
        "latest_chapter": latest_chapter,
        "issues": issues,
    }


def render(report):
    issues = report["issues"]
    lines = [
        f"# 连续性检查（v{report['version']}）",
        "",
        f"- 项目根：`{report['root']}`",
        f"- 章节数：{report['chapter_count']}",
        f"- 问题数：{len(issues)}",
        "",
        "| 级别 | 编号 | 位置 | 问题 |",
        "|---|---|---|---|",
    ]
    if issues:
        for item in issues:
            lines.append(f"| {item['level']} | {item['code']} | `{item['location']}` | {item['message']} |")
    else:
        lines.append("| - | - | - | 未发现机械连续性问题 |")
    lines.extend(["", "语义层的吃书、动机断裂和信息差误判仍需结合正文人工审校。"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=f"网络小说档案连续性检查 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="将报告写入指定文件")
    parser.add_argument("--strict", action="store_true", help="发现任意问题时退出码为1")
    args = parser.parse_args()
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
    has_high = any(item["level"] == "high" for item in report["issues"])
    return 1 if has_high or (args.strict and report["issues"]) else 0


if __name__ == "__main__":
    sys.exit(main())
