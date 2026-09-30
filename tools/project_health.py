# -*- coding: utf-8 -*-
"""统一小说项目健康检查（v7.33）。

把项目体检、档案连续性、元数据、审校断点和实体台账汇总成一个报告；只读，
不替作者修改正文或 canonical 档案。适合开写前、交接时和发布前运行。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import SKILL_VERSION
from continuity_check import check as continuity_check
from entity_index import build_index
from project_audit import audit as project_audit

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def add_issue(items: list[dict], level: str, code: str, location: str, message: str, source: str) -> None:
    items.append({
        "level": level,
        "code": code,
        "location": location,
        "message": message,
        "source": source,
    })


def health(root: Path) -> dict:
    root = Path(root)
    if not root.is_dir():
        return {
            "version": SKILL_VERSION,
            "root": str(root),
            "ok": False,
            "input_error": True,
            "issues": [{
                "level": "high",
                "code": "ROOT_MISSING",
                "location": str(root),
                "message": "项目根不存在或不是目录",
                "source": "project_health",
            }],
            "stats": {},
        }

    issues: list[dict] = []
    audit = project_audit(root)
    continuity = continuity_check(root)
    for item in audit.get("issues", []):
        add_issue(issues, item["level"], item["code"], item["location"], item["message"], "project_audit")
    for item in continuity.get("issues", []):
        add_issue(issues, item["level"], item["code"], item["location"], item["message"], "continuity_check")

    metadata_path = root / "项目元数据.json"
    metadata = {}
    if not metadata_path.is_file():
        add_issue(
            issues, "low", "PROJECT_METADATA_MISSING", "项目元数据.json",
            "项目未使用 init_project.py 初始化，健康报告缺少书名/题材元数据",
            "project_health",
        )
    else:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
            if not isinstance(metadata, dict):
                raise ValueError("顶层不是对象")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            add_issue(
                issues, "medium", "PROJECT_METADATA_INVALID", "项目元数据.json",
                f"元数据无法解析：{exc}", "project_health",
            )

    placeholder_count = 0
    placeholder_files: list[str] = []
    for path in root.rglob("*.md"):
        if any(part in {".git", "build", "dist"} for part in path.parts):
            continue
        try:
            count = path.read_text(encoding="utf-8-sig", errors="replace").count("[待补充]")
        except OSError:
            continue
        if count:
            placeholder_count += count
            placeholder_files.append(str(path.relative_to(root)))
    if placeholder_count:
        add_issue(
            issues, "low", "PLACEHOLDER_FIELDS", "项目 Markdown",
            f"发现 {placeholder_count} 个 `[待补充]` 字段，初始化项目时属于正常提示，开写前应逐项确认",
            "project_health",
        )

    review_open = 0
    review_path = root / ".story-review" / "state.md"
    if review_path.is_file():
        for line in review_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if line.lstrip().startswith("|") and re.search(r"\|\s*(待办|开放|未处理)\s*\|", line):
                review_open += 1
        if review_open:
            add_issue(
                issues, "medium", "REVIEW_OPEN_ITEMS", ".story-review/state.md",
                f"审校断点仍有 {review_open} 项待办", "project_health",
            )

    entities = build_index(root)
    for item in entities.get("duplicate_aliases", []):
        add_issue(
            issues, "medium", "DUPLICATE_ALIAS", "设定/角色.md",
            f"别名“{item['term']}”同时指向：{'、'.join(item['owners'])}",
            "entity_index",
        )

    counts = {
        level: sum(1 for item in issues if item["level"] == level)
        for level in ("high", "medium", "low")
    }
    stats = {
        "chapter_count": audit.get("stats", {}).get("chapter_count", 0),
        "entity_count": entities.get("entity_count", 0),
        "placeholder_count": placeholder_count,
        "placeholder_files": placeholder_files,
        "review_open_items": review_open,
        "issue_counts": counts,
        "metadata": metadata,
    }
    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "ok": not any(item["level"] == "high" for item in issues),
        "input_error": False,
        "issues": issues,
        "stats": stats,
    }


def render(report: dict) -> str:
    stats = report.get("stats", {})
    counts = stats.get("issue_counts", {})
    lines = [
        f"# 项目健康报告（v{report['version']}）",
        "",
        f"- 项目根：`{report['root']}`",
        f"- 章节：{stats.get('chapter_count', 0)}；实体：{stats.get('entity_count', 0)}；待补充字段：{stats.get('placeholder_count', 0)}；审校待办：{stats.get('review_open_items', 0)}",
        f"- 风险计数：高 {counts.get('high', 0)} / 中 {counts.get('medium', 0)} / 低 {counts.get('low', 0)}",
        "",
        "## 结论",
        "",
        ("存在高风险结构问题，先处理后再进入续写。" if not report["ok"] else
         "未发现高风险结构问题，可继续做人工语义审校或开始续写。"),
        "",
        "## 问题清单",
        "",
        "| 级别 | 来源 | 编号 | 位置 | 问题 |",
        "|---|---|---|---|---|",
    ]
    if report["issues"]:
        for item in report["issues"]:
            lines.append(
                f"| {item['level']} | {item['source']} | {item['code']} | "
                f"`{item['location']}` | {item['message']} |"
            )
    else:
        lines.append("| - | - | - | - | 未发现问题 |")
    lines.extend([
        "",
        "## 建议顺序",
        "",
        "1. 先处理 high；2. 再确认 medium；3. 最后清理低风险待补充字段；4. 重新运行本报告。",
        "",
        "本报告只读；文学动机、信息差和关系变化仍需结合正文人工确认。",
    ])
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"统一小说项目健康检查 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="输出报告文件")
    parser.add_argument("--strict", action="store_true", help="任意问题均以退出码1返回")
    args = parser.parse_args(argv)
    report = health(Path(args.project).expanduser())
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"健康报告已写入：{target}")
    else:
        print(output, end="")
    if report.get("input_error"):
        return 2
    return 1 if (
        (args.strict and report["issues"])
        or any(item["level"] == "high" for item in report["issues"])
    ) else 0


if __name__ == "__main__":
    sys.exit(main())
