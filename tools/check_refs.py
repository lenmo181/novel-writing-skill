# -*- coding: utf-8 -*-
"""
check_refs.py — 技能包内相对引用完整性检查（v7.4）
用法: python check_refs.py [技能包根目录]   （默认取本脚本的上一级目录）

做一件事：扫描技能包内的 .md 文件，抽出其中被引用的**技能包内相对路径**
（SKILL.md / references/ / templates/ / tools/ / versions/），校验目标是否存在，
输出悬空清单。

口径声明（避免误判）:
  · 只校验「文件/目录是否存在」，**不校验脚本参数**（如 `--quote`、`--min` 的含义与取值）
  · 运行时路径（mind/、书稿/、大纲/、设定/、封面/、拆文库/、.story-review/）是
    **项目侧**路径，技能包里本来就没有 → 白名单跳过
  · 外部能力（$story-cover、$imagegen、ImageMagick 等）非本地路径 → 跳过
  · versions/ 是冻结存档，**不参与扫描**（但别处对 versions/ 的引用会被校验）

退出码: 0=无悬空引用, 1=存在悬空引用
"""
import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 技能包内可校验的引用前缀
CHECK_PREFIXES = ("references/", "templates/", "tools/", "versions/")

# 项目侧运行时路径 / 外部能力：跳过不校验
SKIP_PREFIXES = ("mind/", "书稿/", "大纲/", "设定/", "封面/", "拆文库/",
                 ".story-review/", ".zcode/", "workspace/", "node_modules/")

# 被引用的候选路径：以 .md / .py 结尾的相对路径或 SKILL.md
REF_RE = re.compile(
    r"(?:SKILL\.md"
    r"|(?:references|templates|tools|versions)/[^\s`\"'（）()\[\]【】《》<>、，。；：!?！？]+?\.(?:md|py)"
    r")")

# 扫描时排除的目录（历史存档 / 缓存）
SKIP_DIRS = {"versions", ".git", "__pycache__", ".v2c", ".video_agent"}


def iter_md_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def strip_trailing(cand):
    return cand.rstrip("。，、；：!?！？*_`\"'）)】》>.")


def is_skipped(rel):
    return rel.startswith(SKIP_PREFIXES)


def check(root):
    root = os.path.abspath(root)
    dangling, checked = [], 0
    seen = set()

    for path in sorted(iter_md_files(root)):
        rel_file = os.path.relpath(path, root).replace("\\", "/")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                for m in REF_RE.finditer(line):
                    cand = strip_trailing(m.group(0))
                    if not cand or is_skipped(cand):
                        continue
                    if not (cand == "SKILL.md" or cand.startswith(CHECK_PREFIXES)):
                        continue
                    checked += 1
                    target = os.path.join(root, cand.replace("/", os.sep))
                    if not os.path.exists(target):
                        key = (rel_file, lineno, cand)
                        if key in seen:
                            continue
                        seen.add(key)
                        dangling.append((rel_file, lineno, cand))

    print(f"扫描根目录: {root}")
    print(f"技能包内相对引用 {checked} 处；跳过项目侧运行时路径与外部能力（mind/、书稿/、大纲/、设定/、封面/、拆文库/、.story-review/ 等）")
    if not dangling:
        print("[✓] 无悬空引用：所有技能包内相对路径均指向存在的文件")
        return 0
    print(f"[✗] 发现 {len(dangling)} 处悬空引用：")
    for rel_file, lineno, cand in dangling:
        print(f"  {rel_file}:{lineno} → {cand}（目标不存在）")
    print("说明：本脚本只校验路径是否存在，不校验脚本参数（如 --quote/--min 的语义）。")
    return 1


def main():
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(
        description="技能包内相对引用完整性检查（只查路径存在性，不查脚本参数）")
    ap.add_argument("root", nargs="?", default=default_root, help="技能包根目录")
    args = ap.parse_args()
    sys.exit(check(args.root))


if __name__ == "__main__":
    main()
