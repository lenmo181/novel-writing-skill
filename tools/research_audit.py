# -*- coding: utf-8 -*-
"""检查研究来源台账的字段、状态和可追溯性（v7.32）。

只读取项目内 Markdown 表格，不联网、不下载来源、不修改研究结论。它负责发现
空来源、重复编号、未核问题和异常状态，不能替作者判断来源是否可信。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import SKILL_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REQUIRED_COLUMNS = ("编号", "来源名称", "类型", "链接/文件路径", "访问日期", "用途", "可用事实", "待核问题", "状态")
VALID_STATUS = {"待核", "已核", "已弃用"}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def cells(line: str) -> list[str]:
    return [item.strip() for item in line.strip().strip("|").split("|")]


def is_separator(row: list[str]) -> bool:
    return bool(row) and all(re.fullmatch(r":?-{2,}:?", item.replace(" ", "")) for item in row)


def table(path: Path) -> tuple[list[str], list[dict]]:
    lines = read_text(path).splitlines()
    header: list[str] = []
    rows: list[dict] = []
    in_table = False
    for line in lines:
        if not line.lstrip().startswith("|"):
            if header:
                break
            continue
        row = cells(line)
        if not header:
            if "编号" in row and "状态" in row:
                header = row
                in_table = True
            continue
        if in_table and is_separator(row):
            continue
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        rows.append({header[index]: row[index] for index in range(len(header))})
    return header, rows


def add_issue(issues: list[dict], level: str, code: str, location: str, message: str) -> None:
    issues.append({"level": level, "code": code, "location": location, "message": message})


def audit(path: Path, project_root: Path | None = None) -> dict:
    path = Path(path).expanduser()
    root = Path(project_root).expanduser() if project_root else path.parent.parent
    issues: list[dict] = []
    if not path.is_file():
        add_issue(issues, "high", "LEDGER_MISSING", str(path), "来源台账不存在")
        return {"version": SKILL_VERSION, "path": str(path), "row_count": 0, "pending_count": 0, "issues": issues}
    header, rows = table(path)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing_columns:
        add_issue(issues, "high", "LEDGER_COLUMNS", str(path), f"缺少字段：{'、'.join(missing_columns)}")
    seen: dict[str, int] = {}
    pending_count = 0
    for index, row in enumerate(rows, 1):
        location = f"{path.name}:{index + 2}"
        identifier = row.get("编号", "").strip()
        status = row.get("状态", "").strip()
        if not identifier or identifier == "[待补充]":
            add_issue(issues, "medium", "SOURCE_ID_MISSING", location, "来源编号为空或仍是待补充")
        elif identifier in seen:
            add_issue(issues, "high", "SOURCE_ID_DUPLICATE", location, f"来源编号重复：{identifier}")
        else:
            seen[identifier] = index
        name = row.get("来源名称", "").strip()
        source_location = row.get("链接/文件路径", "").strip()
        if not name or name == "[待补充]":
            add_issue(issues, "medium", "SOURCE_NAME_MISSING", location, "来源名称为空或仍是待补充")
        if not source_location or source_location == "[待补充]":
            add_issue(issues, "medium", "SOURCE_LOCATION_MISSING", location, "链接/文件路径为空或仍是待补充")
        elif not re.match(r"^(?:https?://|[A-Za-z]:[\\\\/]|/)", source_location):
            candidate = (root / source_location).resolve()
            if not candidate.is_file():
                add_issue(issues, "low", "SOURCE_PATH_UNRESOLVED", location, f"本地来源路径未找到：{source_location}")
        if status not in VALID_STATUS:
            add_issue(issues, "medium", "SOURCE_STATUS_INVALID", location, f"状态不在白名单：{status or '空'}")
        if status == "待核":
            pending_count += 1
        if row.get("待核问题", "").strip() not in ("", "-", "无") and status == "已核":
            add_issue(issues, "low", "SOURCE_UNRESOLVED_NOTE", location, "状态已核但仍保留待核问题")
    return {
        "version": SKILL_VERSION,
        "path": str(path),
        "row_count": len(rows),
        "pending_count": pending_count,
        "issues": issues,
    }


def render(report: dict) -> str:
    lines = [
        f"# 研究来源台账检查（v{report['version']}）",
        "",
        f"- 台账：`{report['path']}`",
        f"- 来源数：{report['row_count']}；待核数：{report['pending_count']}；问题数：{len(report['issues'])}",
        "",
        "| 级别 | 编号 | 位置 | 问题 |",
        "|---|---|---|---|",
    ]
    if report["issues"]:
        lines.extend(
            f"| {item['level']} | {item['code']} | `{item['location']}` | {item['message']} |"
            for item in report["issues"]
        )
    else:
        lines.append("| - | - | - | 未发现台账结构问题 |")
    lines.extend(["", "本检查只验证字段和可追溯性，不替作者判断来源可信度。", ""])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"研究来源台账检查 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--file", default="", help="台账路径；默认 <项目根>/研究/来源台账.md")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="输出报告文件")
    parser.add_argument("--strict", action="store_true", help="发现任意问题时退出码为1")
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    path = Path(args.file).expanduser() if args.file else root / "研究" / "来源台账.md"
    report = audit(path, root)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
        print(f"来源台账报告已写入：{target}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    if not path.is_file():
        return 2
    return 1 if args.strict and report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
