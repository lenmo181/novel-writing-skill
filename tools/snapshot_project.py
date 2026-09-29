# -*- coding: utf-8 -*-
"""小说项目安全快照工具（v7.32）。"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from config import SKILL_VERSION


DEFAULT_DIRS = ("mind", "大纲", "设定", ".story-review", "剧本")


def safe_label(value):
    clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", value.strip())
    return clean.strip("-") or "snapshot"


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def source_files(root: Path, include_chapters=False):
    roots = list(DEFAULT_DIRS)
    if include_chapters:
        roots.append("书稿")
    result = []
    for rel in roots:
        base = root / rel
        if not base.exists():
            continue
        if base.is_file():
            result.append(base)
            continue
        result.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(result)


def create_snapshot(root: Path, label="prechange", include_chapters=False, dry_run=False):
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    target = root / ".novel-snapshots" / f"{timestamp}_{safe_label(label)}"
    files = source_files(root, include_chapters)
    manifest = {
        "version": SKILL_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project": str(root),
        "label": label,
        "include_chapters": include_chapters,
        "files": [],
    }
    for path in files:
        rel = path.relative_to(root)
        manifest["files"].append({
            "path": str(rel),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        })
        if not dry_run:
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target, manifest


def main():
    parser = argparse.ArgumentParser(description=f"创建小说项目安全快照 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--label", default="prechange", help="快照标签")
    parser.add_argument("--include-chapters", action="store_true", help="同时复制书稿/全文")
    parser.add_argument("--dry-run", action="store_true", help="只计算清单，不复制文件")
    args = parser.parse_args()
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"[✗] 项目根不存在或不是目录：{root}")
        return 2
    target, manifest = create_snapshot(root, args.label, args.include_chapters, args.dry_run)
    mode = "预览" if args.dry_run else "已创建"
    print(f"[✓] {mode}快照：{target}")
    print(f"[i] 文件数：{len(manifest['files'])}；包含书稿：{'是' if args.include_chapters else '否'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
