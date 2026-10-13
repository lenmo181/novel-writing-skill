# -*- coding: utf-8 -*-
"""chapter_index.py — 网络小说创作技能 v7.45 章节索引与增量扫描。

为什么需要
----------
面向 200 万-1000 万字（1000-5000 章）时，原来的做法随章数线性退化：

- `context_pack.py` 每找一章就 `书稿/` 全目录 glob 一次，取最近 N 章就是 N 次全目录扫描；
- `full_review.py` / `grep_consistency.py` 每次运行都要把所有正文重读一遍，
  只为拿到「章号 / 标题 / 字数」这类元数据。

本工具把元数据落盘到 `mind/.index/chapters.json`，以 `(mtime_ns, size)` 作为失效判据：
未变更的章节直接复用缓存的 sha256 / 字数 / 标题，只有变更过的才重新读盘。

设计纪律
--------
- **索引永远可以丢**：`mind/.index/` 是缓存，不是事实。删掉后下一次运行会全量重建，
  结果完全一致，只是慢一点。所有调用方必须在索引不可用时回退到全量扫描。
- **不做正文缓存**：只缓存元数据，不复制正文，避免与 `书稿/` 双写产生不一致。
- **变更判据是 mtime_ns + size**，不每次重算 sha256（那等于重新读盘，失去增量意义）；
  sha256 只在文件变更时重算，供 `context_pack.py` 的可追溯清单使用。

用法
----
    python tools/chapter_index.py <项目根> --json        # 建/增量更新索引并输出
    python tools/chapter_index.py <项目根> --rebuild     # 强制全量重建
    python tools/chapter_index.py <项目根> --stats       # 输出命中率统计

退出码：0=成功 / 2=参数或路径错误
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from canonical_parser import CHAPTER_FILE_RE, chapter_files, read_text
from config import SKILL_VERSION

INDEX_DIR = Path("mind") / ".index"
INDEX_NAME = "chapters.json"
INDEX_VERSION = 1


def index_path(root: Path) -> Path:
    return root / INDEX_DIR / INDEX_NAME


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cjk_chars(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or ch in "，。！？；：“”‘’、")


def parse_title(path: Path) -> str:
    """从文件名取章节名（第XXX章_章节名.md → 章节名）；取不到返回空串。"""
    m = CHAPTER_FILE_RE.match(path.name)
    return (m.group(2) or "").strip() if m else ""


def load_index(root: Path) -> dict:
    path = index_path(root)
    if not path.is_file():
        return {"index_version": INDEX_VERSION, "chapters": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"index_version": INDEX_VERSION, "chapters": {}}
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), dict):
        return {"index_version": INDEX_VERSION, "chapters": {}}
    if data.get("index_version") != INDEX_VERSION:
        return {"index_version": INDEX_VERSION, "chapters": {}}
    return data


def save_index(root: Path, data: dict) -> Path:
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["index_version"] = INDEX_VERSION
    data["skill_version"] = SKILL_VERSION
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def scan(root: Path, use_index: bool = True, rebuild: bool = False) -> tuple[list, dict]:
    """扫描项目章节，返回 (记录列表, 统计)。

    记录字段：chapter / path / title / chars / sha256 / size / mtime_ns / from_index
    统计：total / from_index / scanned / removed_entries
    """
    root = Path(root).expanduser().resolve()
    cache = {} if (rebuild or not use_index) else load_index(root).get("chapters", {})
    stat = {"total": 0, "from_index": 0, "scanned": 0, "removed_entries": 0}

    records = []
    seen = set()
    for number, path in chapter_files(root):
        rel = path.relative_to(root).as_posix()
        seen.add(rel)
        try:
            st = path.stat()
        except OSError:
            continue
        key = f"{st.st_mtime_ns}:{st.st_size}"
        cached = cache.get(rel)
        if isinstance(cached, dict) and cached.get("stamp") == key:
            records.append({
                "chapter": number,
                "path": rel,
                "title": cached.get("title", parse_title(path)),
                "chars": int(cached.get("chars", 0)),
                "sha256": cached.get("sha256", ""),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "stamp": key,
                "from_index": True,
            })
            stat["from_index"] += 1
            continue

        text = read_text(path)
        body = "\n".join(ln.strip() for ln in text.splitlines()
                         if ln.strip() and not ln.strip().startswith(("#", ">", "---", "|")))
        records.append({
            "chapter": number,
            "path": rel,
            "title": parse_title(path),
            "chars": _cjk_chars(body),
            "sha256": _sha256_file(path),
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "stamp": key,
            "from_index": False,
        })
        stat["scanned"] += 1

    stat["total"] = len(records)
    stat["removed_entries"] = len([k for k in cache if k not in seen])
    return records, stat


def build(root: Path, rebuild: bool = False) -> dict:
    records, stat = scan(root, rebuild=rebuild)
    data = {
        "chapters": {
            r["path"]: {
                "chapter": r["chapter"], "title": r["title"], "chars": r["chars"],
                "sha256": r["sha256"], "stamp": r["stamp"],
            }
            for r in records
        },
        "stats": stat,
    }
    save_index(root, data)
    return {"records": records, "stats": stat, "index": str(index_path(root).relative_to(root)).replace("\\", "/")}


def lookup(root: Path, number: int, use_index: bool = True) -> str | None:
    """按章号取相对路径，优先走索引（O(1)），否则回退全目录匹配。"""
    if use_index:
        data = load_index(root).get("chapters", {})
        for rel, meta in data.items():
            if isinstance(meta, dict) and meta.get("chapter") == number:
                return rel
    for num, path in chapter_files(root):
        if num == number:
            return path.relative_to(root).as_posix()
    return None


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="章节索引：增量维护章号/标题/字数/sha256")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--rebuild", action="store_true", help="忽略缓存，全量重建")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--stats", action="store_true", help="只输出统计")
    args = parser.parse_args(argv)

    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print("[✗] 项目目录不存在")
        return 2
    result = build(root, rebuild=args.rebuild)
    stat = result["stats"]
    if args.json:
        print(json.dumps({"index": result["index"], "stats": stat,
                          "chapters": result["records"]}, ensure_ascii=False, indent=2))
        return 0
    if args.stats:
        print(f"[i] 索引：{result['index']}")
        print(f"    章节 {stat['total']}｜缓存命中 {stat['from_index']}｜重新读盘 {stat['scanned']}｜清理失效条目 {stat['removed_entries']}")
        return 0
    print(f"[✓] 章节索引已更新：{result['index']}")
    print(f"    章节 {stat['total']}｜缓存命中 {stat['from_index']}｜重新读盘 {stat['scanned']}｜清理失效条目 {stat['removed_entries']}")
    print(f"    字数合计 {sum(r['chars'] for r in result['records'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
