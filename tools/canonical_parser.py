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
    """返回 {角色名: {字段..., "_line": 行号}，同时兼容标准列表式与旧表格式。"""
    rows: dict[str, dict] = {}
    current: str | None = None
    table_headers: list[str] | None = None
    role_headers = {"角色", "角色名", "姓名", "人物", "人物名"}
    aliases = {"别名", "别称", "外号"}
    status_fields = {"状态", "当前状态"}
    last_fields = {"最后出场", "末次出场", "最后出现"}
    first_fields = {"首次出场章", "首次出场", "初登场"}
    for lineno, line in enumerate(read_text(path).splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        m = ROLE_HEADING_RE.match(s)
        if m:
            current = m.group(1).strip(" *#")
            table_headers = None
            if current in {"角色状态快照", "角色名"}:
                current = None
            elif current:
                rows.setdefault(current, {"_line": lineno})
            continue

        if "|" in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and not all(set(c.replace(":", "").strip()) <= {"-", ":", " "} for c in cells):
                if any(c in role_headers for c in cells) and any(c in (aliases | status_fields | last_fields | first_fields) for c in cells):
                    table_headers = cells
                    continue
                if table_headers and len(cells) >= len(table_headers):
                    role_index = next((i for i, c in enumerate(table_headers) if c in role_headers), None)
                    if role_index is not None and role_index < len(cells):
                        name = cells[role_index].strip()
                        if name and name not in role_headers:
                            record = rows.setdefault(name, {"_line": lineno})
                            for i, header in enumerate(table_headers):
                                if i >= len(cells):
                                    break
                                value = cells[i].strip()
                                if not value:
                                    continue
                                if header in aliases:
                                    record["别名"] = value
                                elif header in status_fields:
                                    record["状态"] = value
                                elif header in last_fields:
                                    record["最后出场"] = value
                                elif header in first_fields:
                                    record["首次出场章"] = value
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
