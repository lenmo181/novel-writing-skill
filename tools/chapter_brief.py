# -*- coding: utf-8 -*-
"""生成写前章节任务卡（v7.52）。

任务卡是写作前的可追溯输入，不是剧情生成器。它只读取项目中已经落盘的
正文、回顾、章纲、卷纲、场景纲和 mind 档案；缺少资料时返回 ``needs_input``，
不把计划中的事件当成已经发生的事实。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from canonical_parser import chapter_body, chapter_files, parse_role_snapshot, read_text
from config import SKILL_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


CHAPTER_RE = re.compile(r"第\s*0*(\d{1,6})\s*[章回节]")
EMPTY = {"", "-", "—", "暂无", "无", "[待补充]", "待补充"}


def present(value: str) -> bool:
    return str(value or "").strip() not in EMPTY


def parse_number(value: str) -> int | None:
    match = CHAPTER_RE.search(str(value or ""))
    if match:
        return int(match.group(1))
    match = re.search(r"(?<!\d)(\d{1,6})(?!\d)", str(value or ""))
    return int(match.group(1)) if match else None


def parse_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """读取简单 Markdown 表格，按表头名字返回行；不猜测非表格正文。"""
    lines = read_text(path).splitlines() if path.is_file() else []
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    for line in lines:
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(not cell for cell in cells):
            continue
        if all(not re.search(r"[\w\u4e00-\u9fff]", cell.replace(":", ""))
               for cell in cells):
            continue
        if all(cell and set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if not headers:
            headers = cells
            continue
        if len(cells) != len(headers) or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append({header: cells[index] if index < len(cells) else ""
                     for index, header in enumerate(headers)})
    return headers, rows


def source_record(root: Path, path: Path, role: str) -> dict:
    try:
        raw = path.read_bytes()
        return {
            "path": path.relative_to(root).as_posix(),
            "role": role,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "chars": len(read_text(path)),
        }
    except (OSError, ValueError):
        return {"path": str(path), "role": role, "sha256": "", "chars": 0,
                "error": "读取失败"}


def _row_for(rows: list[dict[str, str]], chapter: int) -> dict[str, str]:
    for row in rows:
        if parse_number(row.get("章号", "")) == chapter:
            return row
    return {}


def _volume_for(rows: list[dict[str, str]], chapter: int) -> dict[str, str]:
    for row in rows:
        span = row.get("起止章", "")
        nums = [int(value) for value in re.findall(r"\d+", span)]
        if len(nums) >= 2 and nums[0] <= chapter <= nums[1]:
            return row
        if parse_number(row.get("卷号", "")) == chapter:
            return row
    return {}


def _split_people(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、，,;；/／|]", value or "")
            if item.strip() and item.strip() not in EMPTY]


def _previous(root: Path, chapter: int) -> dict:
    previous = [(number, path) for number, path in chapter_files(root) if number < chapter]
    if not previous:
        return {"chapter": None, "path": "", "tail": "", "review": ""}
    number, path = previous[-1]
    body = chapter_body(path) or read_text(path)
    review_path = root / "mind" / "回顾" / f"第{number:03d}章回顾.md"
    return {
        "chapter": number,
        "path": path.relative_to(root).as_posix(),
        "tail": body[-1200:],
        "review": read_text(review_path) if review_path.is_file() else "",
    }


def build_brief(root: Path, chapter: int) -> dict:
    root = Path(root).resolve()
    scene_path = root / "大纲" / "场景纲.md"
    chapter_outline_path = root / "大纲" / "章纲.md"
    volume_outline_path = root / "大纲" / "卷纲.md"
    timeline_path = root / "mind" / "时间线.md"
    roles_path = root / "mind" / "角色状态快照.md"
    foreshadow_path = root / "mind" / "伏笔追踪表.md"
    locks_path = root / "mind" / "剧情走向锁定.md"
    chapter_row = _row_for(parse_table(chapter_outline_path)[1], chapter)
    volume_row = {}
    if volume_outline_path.is_file():
        volume_row = _volume_for(parse_table(volume_outline_path)[1], chapter)
    scene_headers, scene_rows = parse_table(scene_path)
    scene_rows = [row for row in scene_rows if parse_number(row.get("章号", "")) == chapter]
    timeline_rows = parse_table(timeline_path)[1]
    timeline_row = _row_for(timeline_rows, chapter)
    previous = _previous(root, chapter)
    roles = parse_role_snapshot(roles_path) if roles_path.is_file() else {}
    scene_people: list[str] = []
    for row in scene_rows:
        for name in _split_people(row.get("在场人物", "")):
            if name not in scene_people:
                scene_people.append(name)
    if not scene_people:
        scene_people = list(roles)

    role_states = {}
    for name in scene_people:
        state = roles.get(name)
        if state:
            role_states[name] = {
                key: value for key, value in state.items() if not key.startswith("_")
            }

    foreshadows = []
    for row in parse_table(foreshadow_path)[1] if foreshadow_path.is_file() else []:
        planted = parse_number(row.get("埋设章", ""))
        planned = parse_number(row.get("预计回收章", ""))
        if planted == chapter or planned == chapter or row.get("状态") in {"未回收", "部分回收"}:
            foreshadows.append(row)

    sources = []
    for path, role in (
        (chapter_outline_path, "chapter_outline"),
        (volume_outline_path, "volume_outline"),
        (scene_path, "scene_outline"),
        (timeline_path, "timeline"),
        (roles_path, "role_state"),
        (foreshadow_path, "foreshadow"),
        (locks_path, "plot_lock"),
    ):
        if path.is_file():
            sources.append(source_record(root, path, role))
    if previous.get("path"):
        sources.append(source_record(root, root / previous["path"], "previous_chapter"))
    if previous.get("chapter"):
        previous_review = root / "mind" / "回顾" / f"第{previous['chapter']:03d}章回顾.md"
        if previous_review.is_file():
            sources.append(source_record(root, previous_review, "previous_review"))

    locations = [row.get("地点/时间", "") for row in scene_rows]
    current_location = locations[0] if locations else ""
    carry_event = (scene_rows[0].get("承接事件", "") if scene_rows else "")
    previous_event = previous.get("review", "").strip() or previous.get("tail", "").strip()
    next_direction = (scene_rows[-1].get("离开钩子", "") if scene_rows else
                      chapter_row.get("章末钩子类型与指纹", ""))
    required = {
        "chapter_outline": bool(chapter_row),
        "volume_outline": bool(volume_row),
        "scene_outline": bool(scene_rows),
        "previous_event": chapter == 1 or bool(previous_event),
        "current_time_or_location": present(timeline_row.get("故事内时间", "")) or present(current_location),
        "scene_people": bool(scene_people),
        "chapter_goal": present(chapter_row.get("本章目标", "")),
        "conflict": present(chapter_row.get("冲突/代价", "")),
        "next_direction": present(next_direction),
    }
    missing = [name for name, present in required.items() if not present]
    return {
        "version": SKILL_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project": str(root),
        "chapter": chapter,
        "status": "ready" if not missing else "needs_input",
        "missing": missing,
        "volume": volume_row,
        "previous": previous,
        "current": {
            "story_time": timeline_row.get("故事内时间", ""),
            "location": current_location,
            "people": scene_people,
            "goal": chapter_row.get("本章目标", ""),
            "conflict": chapter_row.get("冲突/代价", ""),
            "carry_event": carry_event,
            "chapter_hook": chapter_row.get("章末钩子类型与指纹", ""),
        },
        "role_states": role_states,
        "known_information": {name: state.get("知情", "") for name, state in role_states.items()},
        "scene_order": scene_rows,
        "foreshadows": foreshadows,
        "plot_locks": read_text(locks_path) if locks_path.is_file() else "",
        "next_direction": next_direction,
        "required_fields": required,
        "sources": sources,
        "semantic_boundary": (
            "本卡只证明资料来源和结构完整性；人物动机、信息是否合理、幽默自然度、"
            "因果与视角语义仍须由 AI/人工审校并提供第14-30项证据。"
        ),
    }


def render_markdown(brief: dict) -> str:
    current = brief["current"]
    missing_lines = [f"- {item}" for item in brief.get("missing", [])] or ["- 无"]
    lines = [
        f"# 第{brief['chapter']:03d}章任务卡（v{brief['version']}）",
        "",
        f"- 状态：`{brief['status']}`",
        f"- 当前卷：{brief.get('volume', {}).get('卷号', '待补')}",
        f"- 故事时间：{current.get('story_time') or '待补'}",
        f"- 地点：{current.get('location') or '待补'}",
        f"- 在场人物：{'、'.join(current.get('people') or []) or '待补'}",
        f"- 本章目标：{current.get('goal') or '待补'}",
        f"- 冲突/代价：{current.get('conflict') or '待补'}",
        f"- 上一章最后事实：{brief.get('previous', {}).get('tail', '').strip()[-500:] or '首章'}",
        f"- 下章方向：{brief.get('next_direction') or '待补'}",
        "",
        "## 缺口",
        "",
        *missing_lines,
        "",
        "## 来源",
        "",
        "| 角色 | 路径 | SHA-256 |",
        "|---|---|---|",
    ]
    lines.extend(f"| {item['role']} | `{item['path']}` | `{item['sha256'][:16]}` |"
                 for item in brief.get("sources", []))
    lines.extend(["", "> " + brief["semantic_boundary"], ""])
    return "\n".join(lines)


def write_brief(root: Path, brief: dict, output: Path | None = None, fmt: str = "json") -> Path:
    target = output or root / "mind" / "章节任务卡" / f"第{brief['chapter']:03d}章任务卡.{fmt}"
    target = Path(target).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(brief, ensure_ascii=False, indent=2) if fmt == "json" else render_markdown(brief)
    target.write_text(content + "\n", encoding="utf-8")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"生成写前章节任务卡 v{SKILL_VERSION}")
    parser.add_argument("project")
    parser.add_argument("chapter", type=int)
    parser.add_argument("--write", action="store_true", help="写入 mind/章节任务卡/；默认只输出")
    parser.add_argument("--out", default="", help="显式输出路径；传入即写入")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir() or args.chapter < 1:
        print("[✗] 项目目录或章节号非法")
        return 2
    brief = build_brief(root, args.chapter)
    if args.write or args.out:
        target = write_brief(root, brief, Path(args.out) if args.out else None, args.format)
        print(f"[✓] 章节任务卡已写入：{target}")
    else:
        print(json.dumps(brief, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(brief))
    return 0 if brief["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
