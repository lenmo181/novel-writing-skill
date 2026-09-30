# -*- coding: utf-8 -*-
"""为续写、审校和接手旧书生成可追溯上下文包（v7.33）。

只读取项目内 canonical 档案与指定章节，不调用外部模型，不把上下文写入技能目录。
每个文件附 SHA-256、字符数和截断标记，方便跨会话复核来源。
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from config import DEFAULT_CONTEXT_MAX_CHARS, DEFAULT_CONTEXT_RECENT_CHAPTERS, SKILL_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


CANONICAL_FILES = (
    "mind/章节目录.md",
    "mind/角色状态快照.md",
    "mind/伏笔追踪表.md",
    "mind/时间线.md",
    "mind/剧情走向锁定.md",
    "mind/作者记忆.md",
    "大纲/总纲.md",
    "大纲/卷纲.md",
    "大纲/章纲.md",
    "大纲/场景纲.md",
    "设定/世界观.md",
    "设定/角色.md",
    "设定/金手指.md",
    "设定/文风样本.md",
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def chapter_path(root: Path, number: int):
    pattern = re.compile(rf"^第0*{number}章(?:[_\-\s]+.*)?\.(?:md|txt)$", re.I)
    matches = [path for path in (root / "书稿").glob("*") if path.is_file() and pattern.match(path.name)]
    return sorted(matches)[0] if matches else None


def review_path(root: Path, number: int):
    path = root / "mind" / "回顾" / f"第{number:03d}章回顾.md"
    return path if path.is_file() else None


def read_entry(root: Path, path: Path, limit: int, role: str):
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return {
            "path": str(path.relative_to(root)),
            "role": role,
            "error": str(exc),
            "chars": 0,
            "sha256": "",
            "truncated": False,
            "content": "",
        }
    truncated = len(content) > limit
    return {
        "path": str(path.relative_to(root)),
        "role": role,
        "chars": len(content),
        "sha256": sha256_bytes(raw),
        "truncated": truncated,
        "content": content[:limit] if truncated else content,
    }


def build_pack(root: Path, chapter=None, recent=DEFAULT_CONTEXT_RECENT_CHAPTERS,
               max_chars=DEFAULT_CONTEXT_MAX_CHARS):
    selected = []
    seen = set()
    def add(rel, role, limit=max_chars):
        path = root / rel
        if not path.is_file() or str(path) in seen:
            return
        seen.add(str(path))
        selected.append(read_entry(root, path, limit, role))

    for rel in CANONICAL_FILES:
        add(rel, "canonical")

    if chapter is not None:
        add(f"mind/回顾/第{chapter:03d}章回顾.md", "current-review")
        current = chapter_path(root, chapter)
        if current:
            add(str(current.relative_to(root)), "current-chapter", max_chars * 2)
        for number in range(max(1, chapter - recent), chapter):
            path = chapter_path(root, number)
            if path:
                add(str(path.relative_to(root)), "recent-chapter", max_chars)
            review = review_path(root, number)
            if review:
                add(str(review.relative_to(root)), "recent-review", max_chars)

    return {
        "version": SKILL_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": str(root),
        "chapter": chapter,
        "recent": recent,
        "max_chars": max_chars,
        "files": selected,
    }


def render_markdown(pack):
    lines = [
        f"# 上下文包（v{pack['version']}）",
        "",
        f"- 项目根：`{pack['root']}`",
        f"- 目标章节：{pack['chapter'] or '未指定'}",
        f"- 生成时间：{pack['generated_at']}",
        f"- 文件数：{len(pack['files'])}",
        "",
        "## 来源清单",
        "",
        "| 角色 | 路径 | 字符数 | SHA-256 | 截断 |",
        "|---|---|---:|---|---|",
    ]
    for item in pack["files"]:
        lines.append(f"| {item['role']} | `{item['path']}` | {item['chars']} | `{item['sha256'][:16]}` | {'是' if item.get('truncated') else '否'} |")
    for item in pack["files"]:
        lines.extend(["", f"## {item['path']}", "", f"> 角色：{item['role']}；SHA-256：`{item['sha256']}`"])
        if item.get("error"):
            lines.extend(["", f"读取失败：{item['error']}"])
        else:
            if item.get("truncated"):
                lines.extend(["", "> 内容已按上下文预算截断；需要完整文件时按路径回读。"])
            lines.extend(["", "```markdown", item["content"], "```"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=f"生成可追溯小说上下文包 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--chapter", type=int, default=None, help="目标章节号")
    parser.add_argument("--recent", type=int, default=DEFAULT_CONTEXT_RECENT_CHAPTERS, help=f"附带前几章（默认{DEFAULT_CONTEXT_RECENT_CHAPTERS}）")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_CONTEXT_MAX_CHARS, help=f"每个档案最多字符数（默认{DEFAULT_CONTEXT_MAX_CHARS}）")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--out", default="", help="输出文件；不传则打印到标准输出")
    args = parser.parse_args()
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"[✗] 项目根不存在或不是目录：{root}")
        return 2
    if args.recent < 0 or args.max_chars < 200:
        print("[✗] --recent 必须不小于0，--max-chars 必须不小于200")
        return 2
    pack = build_pack(root, args.chapter, args.recent, args.max_chars)
    output = json.dumps(pack, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(pack)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"上下文包已写入：{target}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
