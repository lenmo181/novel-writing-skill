# -*- coding: utf-8 -*-
"""网络小说项目结构体检（v7.30）。

只读扫描项目目录，检查目录骨架、章节编号、章节目录与进度行。
不猜测缺失内容，不修改项目文件；适合作为写作前置和接手旧书的第一道体检。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from config import SKILL_VERSION


CN_NUM_CLASS = "0-9零一二两三四五六七八九十百千万"
CHAPTER_RE = re.compile(rf"^第0*([{CN_NUM_CLASS}]+)[章节回](?:[_\-\s]+(.*?))?\.(?:md|txt)$", re.I)
TITLE_RE = re.compile(rf"^#{{0,6}}\s*第0*([{CN_NUM_CLASS}]+)章(?:\s+(.+?))?\s*$")


def chap_num(s: str) -> int:
    """章号转整数：阿拉伯直转，中文数字（第十二章）经 gen_index.cn_to_int（v7.30：
    旧书常用中文数字章号/「回」体文件名，此前口径过窄整书识别不出，误报 NO_CHAPTERS）。"""
    try:
        return int(s)
    except ValueError:
        from gen_index import cn_to_int
        return cn_to_int(s)
PROGRESS_RE = re.compile(r"已完成至第\s*0*(\d+)章")
NEXT_RE = re.compile(r"下一章为第\s*0*(\d+)章")

REQUIRED_DIRS = ("书稿", "大纲", "设定", "mind")
REQUIRED_FILES = (
    "大纲/总纲.md",
    "大纲/卷纲.md",
    "大纲/章纲.md",
    "大纲/场景纲.md",
    "设定/世界观.md",
    "设定/角色.md",
    "mind/章节目录.md",
)


def parse_chapter_filename(path: Path):
    match = CHAPTER_RE.match(path.name)
    if not match:
        return None
    return chap_num(match.group(1)), (match.group(2) or "").strip()


def parse_title_line(path: Path):
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            match = TITLE_RE.match(line)
            if match:
                return chap_num(match.group(1)), (match.group(2) or "").strip()
            break
    except (OSError, UnicodeError):
        return None
    return None


def chapter_files(root: Path):
    result = []
    book_dir = root / "书稿"
    if not book_dir.is_dir():
        return result
    for path in sorted(book_dir.iterdir()):
        if path.is_file():
            parsed = parse_chapter_filename(path)
            if parsed:
                num, title = parsed
                result.append({
                    "num": num,
                    "title": title,
                    "path": path,
                    "title_line": parse_title_line(path),
                })
    return result


def toc_rows(path: Path):
    rows = {}
    if not path.is_file():
        return rows
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return rows
    for line in lines:
        if not line.lstrip().startswith("|") or re.match(r"^\s*\|?\s*-+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        rows[int(cells[0])] = cells[1]
    return rows


def add_issue(issues, level, code, location, message):
    issues.append({
        "level": level,
        "code": code,
        "location": location,
        "message": message,
    })


def audit(root: Path):
    issues = []
    stats = {
        "chapter_count": 0,
        "chapter_numbers": [],
        "toc_count": 0,
        "missing_dirs": [],
        "missing_files": [],
    }
    if not root.exists() or not root.is_dir():
        add_issue(issues, "high", "ROOT_MISSING", str(root), "项目根不存在或不是目录")
        return {"version": SKILL_VERSION, "root": str(root), "issues": issues, "stats": stats}

    for name in REQUIRED_DIRS:
        if not (root / name).is_dir():
            stats["missing_dirs"].append(name)
            add_issue(issues, "high", "DIR_MISSING", name, f"缺少必需目录：{name}/")

    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            stats["missing_files"].append(rel)
            add_issue(issues, "medium", "FILE_MISSING", rel, f"缺少建议档案：{rel}")

    chapters = chapter_files(root)
    numbers = [row["num"] for row in chapters]
    stats["chapter_count"] = len(chapters)
    stats["chapter_numbers"] = numbers
    if not chapters:
        add_issue(issues, "medium", "NO_CHAPTERS", "书稿/", "未发现符合“第XXX章_标题.md”格式的章节文件")
    else:
        counts = {}
        for number in numbers:
            counts[number] = counts.get(number, 0) + 1
        duplicates = sorted(num for num, count in counts.items() if count > 1)
        if duplicates:
            add_issue(issues, "high", "DUPLICATE_CHAPTER", "书稿/", f"章节编号重复：{duplicates}")
        expected = set(range(min(numbers), max(numbers) + 1))
        gaps = sorted(expected - set(numbers))
        if gaps:
            add_issue(issues, "high", "CHAPTER_GAP", "书稿/", f"章节编号存在断档：{gaps}")

        for row in chapters:
            title_line = row.get("title_line")
            if not title_line:
                add_issue(issues, "medium", "TITLE_MISSING", str(row["path"].relative_to(root)), "首行未找到章节标题")
                continue
            line_num, line_title = title_line
            if line_num != row["num"]:
                add_issue(issues, "high", "TITLE_NUMBER_MISMATCH", str(row["path"].relative_to(root)),
                          f"文件名是第{row['num']}章，正文标题是第{line_num}章")
            if row["title"] and line_title and row["title"] != line_title:
                add_issue(issues, "low", "TITLE_MISMATCH", str(row["path"].relative_to(root)),
                          f"文件名标题“{row['title']}”与首行标题“{line_title}”不一致")

    toc_path = root / "mind" / "章节目录.md"
    toc = toc_rows(toc_path)
    stats["toc_count"] = len(toc)
    if toc and chapters:
        actual_set = set(numbers)
        toc_set = set(toc)
        missing = sorted(actual_set - toc_set)
        extra = sorted(toc_set - actual_set)
        if missing:
            add_issue(issues, "medium", "TOC_MISSING", "mind/章节目录.md", f"目录缺少章节：{missing}")
        if extra:
            add_issue(issues, "low", "TOC_ORPHAN", "mind/章节目录.md", f"目录存在无对应正文的章节：{extra}")

    if toc_path.is_file():
        try:
            toc_text = toc_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            toc_text = ""
        latest = max(numbers) if numbers else None
        progress = PROGRESS_RE.search(toc_text)
        next_chapter = NEXT_RE.search(toc_text)
        if latest is not None and progress and int(progress.group(1)) != latest:
            add_issue(issues, "medium", "PROGRESS_STALE", "mind/章节目录.md",
                      f"进度行写到第{int(progress.group(1))}章，实际最新章节为第{latest}章")
        if latest is not None and next_chapter and int(next_chapter.group(1)) != latest + 1:
            add_issue(issues, "medium", "NEXT_STALE", "mind/章节目录.md",
                      f"下一章写为第{int(next_chapter.group(1))}章，实际应为第{latest + 1}章")

    if (root / "剧本").is_dir() and chapters:
        script_nums = set()
        for path in (root / "剧本").iterdir():
            match = re.match(r"^第0*(\d+)章", path.name)
            if match:
                script_nums.add(int(match.group(1)))
        missing_scripts = sorted(set(numbers) - script_nums)
        if missing_scripts:
            add_issue(issues, "low", "SCRIPT_MISSING", "剧本/", f"已有章节尚未发现对应剧本：{missing_scripts[:20]}")

    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "issues": issues,
        "stats": stats,
    }


def render_markdown(report):
    issues = report["issues"]
    stats = report["stats"]
    counts = {level: sum(1 for item in issues if item["level"] == level)
              for level in ("high", "medium", "low")}
    lines = [
        f"# 项目结构体检（v{report['version']}）",
        "",
        f"- 项目根：`{report['root']}`",
        f"- 扫描时间：{report.get('scanned_at', '')}",
        f"- 章节数：{stats['chapter_count']}；目录条目：{stats['toc_count']}",
        f"- 风险计数：高 {counts['high']} / 中 {counts['medium']} / 低 {counts['low']}",
        "",
        "## 结论",
        "",
        ("存在高风险结构问题，先修复再进入自动续写。" if counts["high"] else
         "结构未发现高风险问题，可继续做连续性与语义层体检。"),
        "",
        "## 问题清单",
        "",
        "| 级别 | 编号 | 位置 | 问题 |",
        "|---|---|---|---|",
    ]
    if issues:
        for item in issues:
            lines.append(f"| {item['level']} | {item['code']} | `{item['location']}` | {item['message']} |")
    else:
        lines.append("| - | - | - | 未发现结构问题 |")
    lines.extend(["", "## 使用边界", "", "本报告只读，不替作者补写设定、剧情或档案内容；语义冲突仍需结合正文人工裁定。"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=f"网络小说项目结构体检 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="将报告写入指定文件")
    parser.add_argument("--strict", action="store_true", help="中低风险也以退出码1返回")
    args = parser.parse_args()
    root = Path(args.project).expanduser()
    report = audit(root)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"报告已写入：{target}")
    else:
        print(output, end="")
    has_high = any(item["level"] == "high" for item in report["issues"])
    return 2 if not root.is_dir() else (1 if has_high or (args.strict and report["issues"]) else 0)


if __name__ == "__main__":
    sys.exit(main())
