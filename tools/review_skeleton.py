# -*- coding: utf-8 -*-
"""review_skeleton.py — 网络小说创作技能 v7.44 语义审校骨架生成器。

背景
----
第14-30项语义证据是交付 Gate 的硬门槛，但 `mind/审校/第XXX章审校.json`
此前只能靠 AI 或人工从零手写：漏项、字段名写错、evidence 留空、忘了填
`chapter_sha256`，都会让 Gate 以「格式问题」而不是「内容问题」失败。

本工具按 `schemas/chapter_semantic_review.schema.json` 一次生成 17 项完整骨架：
    - 校验项名称直接取自 `references/核心校验映射.md`（不另备一份清单，防漂移）；
    - 自动算好当前正文的 `chapter_sha256`，避免事后发现正文已变更；
    - 默认 status=revise、evidence 为「待补：<项名>」，因此**骨架绝不会误通过 Gate**；
    - 已存在同名文件时拒绝覆盖，`--force` 才覆盖。

用法
----
    python tools/review_skeleton.py <项目根> <章号>
    python tools/review_skeleton.py <项目根> 12 --out mind/审校/第012章审校.json
    python tools/review_skeleton.py <项目根> 12 --force

退出码：0=已生成 / 1=已存在或内容缺失 / 2=参数或路径错误
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from config import SKILL_VERSION

ROOT = Path(__file__).resolve().parents[1]
MAP_DOC = ROOT / "references" / "核心校验映射.md"
SEMANTIC_CHECKS = list(range(14, 31))


def load_check_names() -> dict:
    """从核心校验映射表读第14-30项名称；读不到时回退为「第N项」。"""
    names = {}
    try:
        text = MAP_DOC.read_text(encoding="utf-8")
    except OSError:
        return names
    for line in text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        try:
            num = int(m.group(1))
        except ValueError:
            continue
        if num in SEMANTIC_CHECKS:
            names[num] = m.group(2)
    return names


def resolve_chapter(root: Path, chapter: int):
    patterns = (f"第{chapter:03d}章*", f"第{chapter}章*")
    for pattern in patterns:
        hits = sorted((root / "书稿").glob(pattern))
        found = next((p for p in hits if p.is_file()), None)
        if found:
            return found
    return None


def build_skeleton(root: Path, chapter: int, chapter_file: Path, status: str) -> dict:
    names = load_check_names()
    digest = hashlib.sha256(chapter_file.read_bytes()).hexdigest()
    checks = {}
    for num in SEMANTIC_CHECKS:
        label = names.get(num, f"第{num}项")
        checks[str(num)] = {
            "status": status,
            "evidence": f"待补：{label}——填写本章的具体证据（引用原文位置，不写结论形容词）",
            "location": "",
            "confidence": 0.0,
            "note": "骨架生成项，未审校",
        }
    return {
        "$schema": "../schemas/chapter_semantic_review.schema.json",
        "version": SKILL_VERSION,
        "chapter": chapter,
        "chapter_sha256": digest,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(chapter_file.relative_to(root)).replace("\\", "/"),
        "checks": checks,
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="生成第14-30项语义审校骨架 JSON")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("chapter", type=int, help="章号，如 12")
    parser.add_argument("--out", default="", help="输出路径；默认 mind/审校/第XXX章审校.json")
    parser.add_argument("--status", default="revise",
                        choices=["revise", "blocked", "warn", "pass", "weak"],
                        help="骨架初始状态；默认 revise，确保骨架不会误通过交付 Gate")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的审校记录")
    args = parser.parse_args(argv)

    root = Path(args.project).expanduser().resolve()
    if not root.is_dir() or args.chapter < 1:
        print("[✗] 项目目录不存在或章号非法")
        return 2

    chapter_file = resolve_chapter(root, args.chapter)
    if chapter_file is None:
        print(f"[✗] 未找到第{args.chapter}章正文（书稿/第XXX章_章节名.md）")
        return 2

    out = Path(args.out).expanduser() if args.out else root / "mind" / "审校" / f"第{args.chapter:03d}章审校.json"
    if not out.is_absolute():
        out = root / out
    if out.exists() and not args.force:
        print(f"[✗] 已存在 {out.relative_to(root)}；加 --force 覆盖，或先备份")
        return 1

    skeleton = build_skeleton(root, args.chapter, chapter_file, args.status)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rel = out.relative_to(root) if out.is_relative_to(root) else out
    print(f"[✓] 骨架已生成：{rel}")
    print(f"    章：第{args.chapter}章（{skeleton['source']}）")
    print(f"    sha256：{skeleton['chapter_sha256'][:16]}…")
    print(f"    覆盖：第14-30项共 {len(SEMANTIC_CHECKS)} 项，初始 status={args.status}")
    if args.status in ("revise", "blocked"):
        print("    提示：默认状态不会通过交付 Gate——逐项填完 evidence 后再跑 chapter_readiness.py")
    if args.status == "weak":
        print("    提示：weak 档表示未经 AI 语义复核，Gate 不卡死但不可作为正式交付结论")
    return 0


if __name__ == "__main__":
    sys.exit(main())
