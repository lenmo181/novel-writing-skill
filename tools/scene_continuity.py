# -*- coding: utf-8 -*-
"""场景锚点与转场连续性检查（v7.52）。

该工具只做可机械验证的结构检查：它不会从正文猜测人物动机，也不会把
“地点/时间”自由文本解析成完整世界模型。没有场景纲时只给出 warning，
以兼容旧项目；新初始化项目应填写扩展锚点列后再进入章节 Gate。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from canonical_parser import parse_role_snapshot, read_text
from chapter_brief import parse_number, parse_table
from config import SKILL_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


BASE_FIELDS = ("章号", "场景", "视角", "地点/时间", "目标", "阻碍", "转折/不可逆变化", "离开钩子")
ANCHOR_FIELDS = ("在场人物", "进入原因", "承接事件", "下一场过渡")
DEATH_MARKS = ("已亡", "已死", "死亡", "身亡", "阵亡", "殒命", "战死", "已殁", "退场")
MEMORY_MARKS = ("回忆", "照片", "录音", "遗像", "尸体", "档案")


def _issue(code: str, level: str, location: str, message: str) -> dict:
    return {"code": code, "level": level, "location": location, "message": message}


def _people(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、，,;；/／|]", value or "") if item.strip()]


def _present(value: str) -> bool:
    return str(value or "").strip() not in {"", "-", "—", "暂无", "无", "[待补充]", "待补充"}


def _same_time(value: str) -> str:
    # 只提取可直接比对的日期/时刻 token；没有明确 token 就不判定“同时”。
    matches = re.findall(r"(?:第\s*\d+天|\d{1,2}[点时]\d{0,2}分?|\d{1,2}月\d{1,2}日)", value or "")
    return " ".join(matches)


def check(root: Path, chapter: int | None = None, strict: bool = False) -> dict:
    root = Path(root).resolve()
    scene_path = root / "大纲" / "场景纲.md"
    if not scene_path.is_file():
        issue = _issue("SCENE_OUTLINE_MISSING", "warning", "大纲/场景纲.md",
                       "未提供场景纲，无法执行场景级锚点检查；旧项目可先补纲")
        return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter,
                "ok": not strict, "errors": [], "warnings": [issue], "rows": 0}

    headers, all_rows = parse_table(scene_path)
    rows = [row for row in all_rows if chapter is None or parse_number(row.get("章号", "")) == chapter]
    if not rows:
        issue = _issue("SCENE_ROWS_MISSING", "warning", "大纲/场景纲.md",
                       f"未找到第{chapter}章场景行" if chapter else "场景纲没有可解析的场景行")
        return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter,
                "ok": not strict, "errors": [], "warnings": [issue], "rows": 0}

    errors: list[dict] = []
    warnings: list[dict] = []
    missing_headers = [field for field in ANCHOR_FIELDS if field not in headers]
    if missing_headers:
        warnings.append(_issue("SCENE_SCHEMA_LEGACY", "warning", "大纲/场景纲.md",
                               "旧格式缺少扩展锚点列：" + "、".join(missing_headers)))

    roles_path = root / "mind" / "角色状态快照.md"
    role_snapshots = parse_role_snapshot(roles_path) if roles_path.is_file() else {}
    dead_roles = {name for name, state in role_snapshots.items()
                  if any(mark in state.get("状态", "") for mark in DEATH_MARKS)}

    grouped: dict[int, list[dict]] = {}
    for index, row in enumerate(rows, 1):
        number = parse_number(row.get("章号", "")) or chapter or 0
        grouped.setdefault(number, []).append(row)
        location = f"大纲/场景纲.md:{index}"
        template_values = [row.get(field, "") for field in BASE_FIELDS if field not in {"章号", "场景"}]
        template_values.extend(row.get(field, "") for field in ANCHOR_FIELDS if field in headers)
        if template_values and not any(_present(value) for value in template_values):
            warnings.append(_issue("SCENE_TEMPLATE_UNFILLED", "warning", location,
                                   "初始化模板场景尚未填写，补完后再进入章节 Gate"))
            continue
        missing = [field for field in BASE_FIELDS if not row.get(field, "").strip() or row.get(field, "").strip() in {"[待补充]", "待补充"}]
        if missing:
            errors.append(_issue("SCENE_ANCHOR_MISSING", "high", location,
                                 "场景锚点缺少：" + "、".join(missing)))
        for field in ANCHOR_FIELDS:
            if field in headers and (not row.get(field, "").strip() or row.get(field, "").strip() in {"[待补充]", "待补充"}):
                errors.append(_issue("SCENE_ANCHOR_MISSING", "high", location,
                                     f"扩展锚点字段“{field}”为空"))
        people = _people(row.get("在场人物", ""))
        if people and dead_roles.intersection(people) and not any(mark in row.get("承接事件", "") for mark in MEMORY_MARKS):
            errors.append(_issue("SCENE_DEAD_ROLE", "high", location,
                                 "已亡/退场角色出现在当前场景：" + "、".join(sorted(dead_roles.intersection(people)))))

    for number, chapter_rows in grouped.items():
        scene_numbers = []
        for row in chapter_rows:
            match = re.search(r"\d+", row.get("场景", ""))
            scene_numbers.append(int(match.group()) if match else None)
        valid = [item for item in scene_numbers if item is not None]
        if len(valid) != len(set(valid)) or valid != sorted(valid):
            errors.append(_issue("SCENE_ORDER", "high", "大纲/场景纲.md",
                                 f"第{number}章场景编号不递增或重复：{scene_numbers}"))
        for previous, current in zip(chapter_rows, chapter_rows[1:]):
            location_changed = previous.get("地点/时间", "") != current.get("地点/时间", "")
            pov_changed = previous.get("视角", "") != current.get("视角", "")
            transition = current.get("进入原因", "") or current.get("承接事件", "") or current.get("下一场过渡", "")
            if (location_changed or pov_changed) and not transition.strip():
                errors.append(_issue("SCENE_TRANSITION_MISSING", "high", "大纲/场景纲.md",
                                     "地点/时间或视角发生变化，但没有进入原因、承接事件或过渡"))
            left = set(_people(previous.get("在场人物", "")))
            right = set(_people(current.get("在场人物", "")))
            if left and right and left.intersection(right) and _same_time(previous.get("地点/时间", "")) == _same_time(current.get("地点/时间", "")) and previous.get("地点/时间", "") != current.get("地点/时间", ""):
                errors.append(_issue("SCENE_DOUBLE_LOCATION", "high", "大纲/场景纲.md",
                                     "同一明确时间点，同一角色被安排在不同地点：" + "、".join(sorted(left.intersection(right)))))

    return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter,
            "ok": not errors and (not strict or not warnings), "errors": errors,
            "warnings": warnings, "rows": len(rows)}


def render(report: dict) -> str:
    lines = [
        f"# 场景连续性检查（v{report['version']}）", "",
        f"- 章节：{report.get('chapter') or '全部'}；场景行：{report.get('rows', 0)}",
        f"- 结论：{'通过' if report['ok'] else '需修复'}", "",
        "| 级别 | 编号 | 位置 | 问题 |", "|---|---|---|---|",
    ]
    issues = report.get("errors", []) + report.get("warnings", [])
    lines.extend(f"| {item['level']} | {item['code']} | `{item['location']}` | {item['message']} |" for item in issues)
    if not issues:
        lines.append("| - | - | - | 未发现机械场景连续性问题 |")
    lines.append("")
    lines.append("本工具只检查结构锚点与明确机械矛盾；人物动机、信息差合理性和文学转场仍需语义审校。")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"场景锚点与转场连续性检查 v{SKILL_VERSION}")
    parser.add_argument("project")
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--strict", action="store_true", help="把旧格式/缺场景 warning 也判失败")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print("[✗] 项目目录不存在")
        return 2
    report = check(root, args.chapter, args.strict)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report), end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
