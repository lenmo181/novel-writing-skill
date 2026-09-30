# -*- coding: utf-8 -*-
"""网络小说档案连续性检查（v7.34）。

聚焦“文件之间对不上”的机械问题：章节标题、时间线顺序、伏笔日期、
角色首末出场章和单章回顾覆盖率。语义冲突仍交给作者或审校流程裁定。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import SKILL_VERSION
from project_audit import chapter_files, add_issue

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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


def check_foreshadows(root, issues):
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
        if len(cells) >= 6 and cells[5] not in ("未回收", "已回收", "已废弃", "待定", "-"):
            add_issue(issues, "low", "FORESHADOW_STATUS", f"mind/伏笔追踪表.md:{index}",
                      f"伏笔状态不在白名单：{cells[5]}")


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


def check(root: Path):
    issues = []
    chapters = chapter_files(root)
    check_timeline(root, issues)
    check_roles(root, issues)
    check_foreshadows(root, issues)
    check_toc_titles(root, chapters, issues)
    check_reviews(root, chapters, issues)
    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "chapter_count": len(chapters),
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
