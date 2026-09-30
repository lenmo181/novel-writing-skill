# -*- coding: utf-8 -*-
"""生成角色/别名/关系/出场台账（v7.33）。

从设定/角色.md 与 mind/角色状态快照.md 读取已有事实，按章节正文统计实际出场。
它只生成报告，不凭正文猜测新设定；未知人物仍由作者确认后写回档案。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import SKILL_VERSION
from project_audit import chapter_files

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


FIELD_RE = re.compile(r"^\s*-\s*([^：:]+)[：:]\s*(.*?)\s*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
SPLIT_RE = re.compile(r"[、,，/；;|]+")
EMPTY_VALUES = {"", "无", "暂无", "待补充", "[待补充]", "-"}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def sections(path: Path) -> list[dict]:
    rows: list[dict] = []
    current = None
    for line in read_text(path).splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            if current:
                rows.append(current)
            current = {"name": heading.group(1).strip(), "fields": {}, "source": str(path)}
            continue
        if current:
            match = FIELD_RE.match(line)
            if match:
                current["fields"][match.group(1).strip()] = match.group(2).strip()
    if current:
        rows.append(current)
    return rows


def split_values(value: str) -> list[str]:
    return [
        item.strip().strip("*_`[]")
        for item in SPLIT_RE.split(value or "")
        if item.strip() and item.strip() not in EMPTY_VALUES
    ]


def count_mentions(content: str, terms: list[str]) -> int:
    """按最长别名优先计数，避免“林”把“林舟”重复算一遍。"""
    if not terms:
        return 0
    pattern = re.compile("|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)))
    return sum(1 for _ in pattern.finditer(content))


def build_index(root: Path) -> dict:
    root = Path(root)
    records: dict[str, dict] = {}
    for rel in ("设定/角色.md", "mind/角色状态快照.md"):
        path = root / rel
        for row in sections(path):
            name = row["name"].strip()
            if name in EMPTY_VALUES or "待补充" in name or name.startswith("角色状态快照"):
                continue
            record = records.setdefault(name, {
                "name": name,
                "aliases": [],
                "fields": {},
                "sources": [],
                "relations": [],
                "mention_count": 0,
                "chapters": [],
            })
            record["sources"].append(rel)
            record["fields"].update(row["fields"])
            record["aliases"] = sorted(
                set(record["aliases"] + split_values(row["fields"].get("别名", "")))
            )
            for key, value in row["fields"].items():
                if "关系" in key or key in {"关联角色", "关联"}:
                    if value not in EMPTY_VALUES:
                        record["relations"].append({
                            "field": key,
                            "value": value,
                            "source": rel,
                        })

    alias_owner: dict[str, str] = {}
    duplicate_aliases: list[dict] = []
    for name, record in records.items():
        terms = [name] + record["aliases"]
        record["terms"] = sorted(
            set(term for term in terms if term not in EMPTY_VALUES),
            key=len,
            reverse=True,
        )
        for term in record["terms"]:
            owner = alias_owner.get(term)
            if owner and owner != name:
                duplicate_aliases.append({"term": term, "owners": [owner, name]})
            else:
                alias_owner[term] = name

    chapters = sorted(chapter_files(root), key=lambda item: item["num"])
    for row in records.values():
        chapter_hits = []
        for chapter in chapters:
            content = read_text(chapter["path"])
            count = count_mentions(content, row["terms"])
            if count:
                chapter_hits.append({"chapter": chapter["num"], "count": count})
        row["chapters"] = chapter_hits
        row["mention_count"] = sum(item["count"] for item in chapter_hits)
        row["first_mention"] = chapter_hits[0]["chapter"] if chapter_hits else None
        row["last_mention"] = chapter_hits[-1]["chapter"] if chapter_hits else None
        row.pop("terms", None)

    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "entity_count": len(records),
        "chapter_count": len(chapters),
        "entities": sorted(
            records.values(),
            key=lambda item: (
                item["first_mention"] is None,
                item["first_mention"] or 10**9,
                item["name"],
            ),
        ),
        "duplicate_aliases": duplicate_aliases,
    }


def _mermaid_label(value: str) -> str:
    return re.sub(r"[\r\n\[\]{}()\"`|]", " ", value).strip()[:36]


def render(report: dict) -> str:
    lines = [
        f"# 实体索引（v{report['version']}）",
        "",
        f"- 项目根：`{report['root']}`",
        f"- 实体数：{report['entity_count']}；扫描章节：{report['chapter_count']}",
        "- 口径：只统计已写入角色档案的姓名与别名；不把正文中的陌生称呼自动登记为角色。",
        "",
        "## 角色/实体台账",
        "",
        "| 实体 | 别名 | 首次实际出场 | 最近实际出场 | 出现次数 | 当前状态 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in report["entities"]:
        fields = item["fields"]
        aliases = "、".join(item["aliases"]) or "无"
        first = f"第{item['first_mention']}章" if item["first_mention"] is not None else "未发现"
        last = f"第{item['last_mention']}章" if item["last_mention"] is not None else "未发现"
        state = fields.get("状态", fields.get("当前状态", "未填写"))
        lines.append(
            f"| {item['name']} | {aliases} | {first} | {last} | "
            f"{item['mention_count']} | {state} |"
        )
    if not report["entities"]:
        lines.append("| - | - | - | - | - | 尚未建立角色档案 |")

    lines.extend(["", "## 关系记录", ""])
    relations = [
        (item["name"], rel["value"])
        for item in report["entities"]
        for rel in item["relations"]
    ]
    if relations:
        lines.extend(["| 来源实体 | 档案中的关系描述 |", "|---|---|"])
        lines.extend(f"| {name} | {value} |" for name, value in relations)
        lines.extend(["", "### 可识别关系图", "", "```mermaid", "graph LR"])
        names = [item["name"] for item in report["entities"]]
        for source, value in relations:
            targets = [name for name in names if name != source and name in value]
            for target in targets:
                source_id = re.sub(r"\W", "_", source)
                target_id = re.sub(r"\W", "_", target)
                lines.append(
                    f"    {source_id} -->|{_mermaid_label(value)}| {target_id}"
                )
        lines.extend(["```", ""])
    else:
        lines.append("尚未在角色档案中发现关系字段；补写 `- 关系：…` 后重新生成。")

    lines.extend(["", "## 数据质量提示", ""])
    if report["duplicate_aliases"]:
        for item in report["duplicate_aliases"]:
            lines.append(
                f"- [中] 别名“{item['term']}”同时归属于："
                f"{'、'.join(item['owners'])}；请确认信息差口径。"
            )
    no_mentions = [
        item["name"] for item in report["entities"] if item["mention_count"] == 0
    ]
    if no_mentions:
        lines.append(
            f"- [低] 已登记但扫描不到正文出场：{'、'.join(no_mentions[:20])}。"
            "可能是尚未出场、别名未登记或章节格式需复核。"
        )
    if not report["duplicate_aliases"] and not no_mentions:
        lines.append("- 未发现别名冲突或已登记实体零出场问题。")
    lines.extend([
        "",
        "本报告不替作者决定角色身份；关系、别名和出场状态需确认后再写回 canonical 档案。",
        "",
    ])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"生成角色别名关系出场台账 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--out", default="", help="输出文件；不传则打印")
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"[✗] 项目根不存在或不是目录：{root}")
        return 2
    report = build_index(root)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else render(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
        print(f"实体索引已写入：{target}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
