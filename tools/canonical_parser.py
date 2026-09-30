# -*- coding: utf-8 -*-
"""Canonical project parsers (v7.39).

统一角色快照、章节号和章节正文的基础解析，避免各工具维护不同语法。
只解析项目已有事实，不猜测新设定。
"""
from __future__ import annotations

import re
from pathlib import Path

FIELD_RE = re.compile(r"^\s*[-*·]?\s*([^：:]{1,32})\s*[：:]\s*(.*?)\s*$")
ROLE_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
CHAPTER_NUM_RE = re.compile(r"第\s*0*(\d{1,6})\s*[章回节]")
CHAPTER_FILE_RE = re.compile(r"^第\s*0*(\d{1,6})\s*[章回节](?:[_\-\s]+(.*?))?\.(?:md|txt)$", re.I)

def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except (OSError, UnicodeDecodeError):
            continue
    return ""

def parse_role_snapshot(path: Path) -> dict[str, dict]:
    """返回 {角色名: {字段..., "_line": 行号}}，与项目标准模板一致。"""
    rows: dict[str, dict] = {}
    current: str | None = None
    for lineno, line in enumerate(read_text(path).splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        m = ROLE_HEADING_RE.match(s)
        if m:
            current = m.group(1).strip(" *#")
            if current in {"角色状态快照", "角色名"}:
                current = None
            elif current:
                rows.setdefault(current, {"_line": lineno})
            continue
        if current is None:
            continue
        fm = FIELD_RE.match(s)
        if fm:
            rows[current][fm.group(1).strip()] = fm.group(2).strip()
    return rows

def parse_chapter_number(value: str) -> int | None:
    m = CHAPTER_NUM_RE.search(value or "")
    return int(m.group(1)) if m else None

def chapter_files(root: Path) -> list[tuple[int, Path]]:
    book = root / "书稿"
    if not book.is_dir():
        return []
    result = []
    for path in book.iterdir():
        if not path.is_file():
            continue
        m = CHAPTER_FILE_RE.match(path.name)
        if m:
            result.append((int(m.group(1)), path))
    return sorted(result, key=lambda item: item[0])

def chapter_body(path: Path) -> str | None:
    try:
        text = read_text(path)
    except OSError:
        return None
    if text == "" and path.stat().st_size:
        return None
    lines = []
    seen_title = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not seen_title and CHAPTER_NUM_RE.match(line.lstrip("#").lstrip()):
            seen_title = True
            continue
        if line.startswith(("#", ">", "---", "|")):
            continue
        lines.append(line)
    return "\n".join(lines)
