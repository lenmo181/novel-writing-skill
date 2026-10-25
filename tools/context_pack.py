# -*- coding: utf-8 -*-
"""为续写、审校和接手旧书生成可追溯上下文包（v7.52）。

默认只读取项目内 canonical 档案与指定章节，不调用外部模型，不把上下文写入技能目录。
若项目明确开启同类小说研究并允许联网，会先刷新 24 小时缓存的结构卡，再把
研究报告作为低权重上下文载荷；未开启或网络失败不阻塞上下文包。
每个文件附 SHA-256、字符数和截断标记，方便跨会话复核来源。
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from config import (DEFAULT_CONTEXT_CURRENT_FLOOR_RATIO, DEFAULT_CONTEXT_MAX_CHARS,
                    DEFAULT_CONTEXT_MAX_TOTAL, DEFAULT_CONTEXT_RECENT_CHAPTERS,
                    SKILL_VERSION)
from canonical_parser import CHAPTER_FILE_RE  # noqa: F401  (保持与章节命名口径同源)
import chapter_index

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


CANONICAL_FILES = (
    "mind/章节目录.md",
    "mind/角色状态快照.md",
    "mind/伏笔追踪表.md",
    "mind/事实台账.md",
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
    "研究/同类小说研究.md",
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def chapter_path(root: Path, number: int):
    """按章号定位章节：优先走章节索引（O(1)），索引不可用时回退全目录匹配。

    v7.45：原实现每次调用都 glob 整个 书稿/，取最近 N 章就是 N 次全目录扫描，
    在千章规模下是 O(N×M) 的 stat 风暴。
    """
    rel = chapter_index.lookup(root, number)
    if rel:
        candidate = root / rel
        if candidate.is_file():
            return candidate
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


# v7.45 上下文预算：角色权重决定总量怎么切。当前章权重最高且有保底，
# 保证预算再紧也不会把「正在写的这一章」挤没。
ROLE_WEIGHTS = {
    "canonical": 1.0,
    "current-chapter": 3.0,
    "current-review": 1.0,
    "recent-chapter": 1.0,
    "recent-review": 0.5,
    "similar-research": 0.5,
}
CURRENT_ROLE = "current-chapter"
BRIEF_ROLE = "chapter-brief"


def maybe_refresh_similar(root: Path) -> dict:
    """按项目显式配置刷新同类研究；配置关闭时绝不联网。"""
    try:
        import similar_novels
        config = similar_novels.load_config(root)
        if not config.get("enabled"):
            return {"status": "disabled"}
        if not config.get("allow_network"):
            return {"status": "network_not_authorized"}
        return similar_novels.research(root, allow_network=True)
    except Exception as exc:  # 研究是可选增强，不能阻塞续写上下文
        return {"status": "error", "message": str(exc)}


def plan_entries(root: Path, chapter, recent: int) -> list:
    """先规划「要放哪些文件、各是什么角色」，不读盘——预算分配需要这一步。"""
    plan = []
    for rel in CANONICAL_FILES:
        if (root / rel).is_file():
            role = "similar-research" if rel == "研究/同类小说研究.md" else "canonical"
            plan.append((rel, role))
    if chapter is None:
        return plan
    brief = root / "mind" / "章节任务卡" / f"第{chapter:03d}章任务卡.json"
    if brief.is_file():
        plan.append((brief.relative_to(root).as_posix(), BRIEF_ROLE))
    review = f"mind/回顾/第{chapter:03d}章回顾.md"
    if (root / review).is_file():
        plan.append((review, "current-review"))
    current = chapter_path(root, chapter)
    if current:
        plan.append((current.relative_to(root).as_posix(), CURRENT_ROLE))
    for number in range(max(1, chapter - recent), chapter):
        path = chapter_path(root, number)
        if path:
            plan.append((path.relative_to(root).as_posix(), "recent-chapter"))
        rev = review_path(root, number)
        if rev:
            plan.append((rev.relative_to(root).as_posix(), "recent-review"))
    return plan


def allocate_limits(plan: list, max_total: int, max_chars: int,
                    floor_ratio: float = DEFAULT_CONTEXT_CURRENT_FLOOR_RATIO) -> dict:
    """按角色权重把总预算切成每角色的单文件上限（再受 max_chars 硬顶约束）。"""
    counts = {}
    for _rel, role in plan:
        counts[role] = counts.get(role, 0) + 1
    weighted = sum(ROLE_WEIGHTS.get(role, 1.0) * count for role, count in counts.items())
    limits = {}
    for role, count in counts.items():
        if count <= 0:
            continue
        share = max_total * ROLE_WEIGHTS.get(role, 1.0) / weighted if weighted else max_chars
        limits[role] = max(200, int(min(max_chars, share / count)))
    # 当前章保底：预算被摊薄时也要留下可读的一截
    if CURRENT_ROLE in limits and max_total:
        floor_limit = int(max_total * floor_ratio)
        limits[CURRENT_ROLE] = max(limits[CURRENT_ROLE], min(max_chars * 2, floor_limit))
    return limits


def build_pack(root: Path, chapter=None, recent=DEFAULT_CONTEXT_RECENT_CHAPTERS,
               max_chars=DEFAULT_CONTEXT_MAX_CHARS, max_total=DEFAULT_CONTEXT_MAX_TOTAL):
    similar_research = maybe_refresh_similar(root)
    plan = plan_entries(root, chapter, recent)
    limits = allocate_limits(plan, max_total, max_chars) if max_total else {}

    selected = []
    seen = set()

    def add(rel, role):
        path = root / rel
        if not path.is_file() or str(path) in seen:
            return
        seen.add(str(path))
        limit = limits.get(role, max_chars * 2 if role == CURRENT_ROLE else max_chars)
        selected.append(read_entry(root, path, limit, role))

    for rel, role in plan:
        add(rel, role)

    # 预算按「实际注入的字符数」计，不是文件原始大小——被截断的部分并没有进上下文
    used = sum(len(item["content"]) for item in selected)
    per_role = {}
    for item in selected:
        per_role[item["role"]] = per_role.get(item["role"], 0) + len(item["content"])
    budget = {
        "max_total": max_total,
        "used": used,
        "raw_chars": sum(item["chars"] for item in selected),
        "within_budget": (not max_total) or used <= max_total,
        "per_role_chars": per_role,
        "limits": limits,
        "truncated_files": [item["path"] for item in selected if item.get("truncated")],
    }

    return {
        "version": SKILL_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": str(root),
        "chapter": chapter,
        "recent": recent,
        "max_chars": max_chars,
        "budget": budget,
        "files": selected,
        "similar_research": similar_research,
    }


def render_markdown(pack):
    lines = [
        f"# 上下文包（v{pack['version']}）",
        "",
        f"- 项目根：`{pack['root']}`",
        f"- 目标章节：{pack['chapter'] or '未指定'}",
        f"- 生成时间：{pack['generated_at']}",
        f"- 文件数：{len(pack['files'])}",
        f"- 同类小说研究：{pack.get('similar_research', {}).get('status', '未执行')}",
    ]
    budget = pack.get("budget")
    if budget:
        lines += [
            f"- 上下文预算：{budget['used']} / {budget['max_total']} 字符"
            f"（{'未超预算' if budget['within_budget'] else '已超预算'}）",
        ]
        if budget["limits"]:
            shown = "；".join(f"{k}={v}" for k, v in sorted(budget["limits"].items()))
            lines.append(f"- 各角色单文件上限：{shown}")
    lines += [
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
    parser.add_argument("--max-total", type=int, default=DEFAULT_CONTEXT_MAX_TOTAL, help=f"上下文包总字符预算（默认{DEFAULT_CONTEXT_MAX_TOTAL}；0 表示不设总量闸门）")
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
    pack = build_pack(root, args.chapter, args.recent, args.max_chars,
                      args.max_total if args.max_total > 0 else 0)
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
