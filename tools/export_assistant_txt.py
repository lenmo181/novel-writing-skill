# -*- coding: utf-8 -*-
"""
export_assistant_txt.py — 合并 书稿/ 为作家助手「本地导入」可用的单文件 txt
用法: python export_assistant_txt.py <项目根> [--out 输出.txt] [--range 1-50,55]
                                      [--encoding utf-8-sig] [--dry-run]
只读 书稿/，唯一写入是导出的 txt（默认 <项目根>/导出/<书名>_作家助手.txt）。
章节切分依据：章节标题独占一行（第X章 标题），作家助手本地导入按此拆分。
退出码: 0=导出成功, 1=写出失败, 2=输入错误（项目/书稿不存在、无章节、参数非法）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CHAPTER_FILE_RE = re.compile(r"第\s*(\d{1,5})\s*章")
TITLE_LINE_RE = re.compile(
    r"^#{0,3}\s*第\s*([0-9]{1,5})\s*章\s*[:：.、_\-\s]*\s*(.*)$"
)
ARTIFACT_RE = re.compile(r"^(#{1,6}\s+|```|---+|\*\*\*+|>\s*$)")
ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb18030")


def parse_range(spec: str) -> set:
    """解析 '1-50,55' 形式的章号选择，返回章号集合；非法抛 ValueError。"""
    picked: set = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo, _, hi = token.partition("-")
            lo_int, hi_int = int(lo), int(hi)
            if lo_int < 1 or lo_int > hi_int:
                raise ValueError(f"非法区间：{token}")
            picked.update(range(lo_int, hi_int + 1))
        else:
            num = int(token)
            if num < 1:
                raise ValueError(f"非法章号：{token}")
            picked.add(num)
    if not picked:
        raise ValueError("区间为空")
    return picked


def chapter_number(path: Path, head: str) -> int | None:
    """章号优先取文件名，取不到再从正文标题行推断。"""
    m = CHAPTER_FILE_RE.search(path.name)
    if m:
        return int(m.group(1))
    for line in head.splitlines():
        m = TITLE_LINE_RE.match(line.strip())
        if m:
            return int(m.group(1))
    return None


def read_chapter(path: Path) -> tuple[int | None, str, str]:
    """读取一章，返回 (章号, 标题行, 正文)。标题行缺失时从文件名合成。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [l.rstrip() for l in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    title = ""
    m = TITLE_LINE_RE.match(lines[0].strip()) if lines else None
    if m:
        num = int(m.group(1))
        name = m.group(2).strip()
        title = f"第{num}章 {name}".rstrip()
        lines = lines[1:]
    else:
        stem = re.split(r"[_.]", path.stem, maxsplit=1)[-1].strip()
        if CHAPTER_FILE_RE.fullmatch(stem):
            stem = ""
        m_file = CHAPTER_FILE_RE.search(path.name)
        prefix = f"第{int(m_file.group(1))}章" if m_file else ""
        title = f"{prefix} {stem}".strip()
    while lines and not lines[0].strip():
        lines.pop(0)
    in_fence = False
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence  # 围栏区域（含内容）整体视为 markdown 残留
            continue
        if in_fence or ARTIFACT_RE.match(stripped):
            continue
        body_lines.append(line)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    return chapter_number(path, text), title, "\n".join(body_lines)


def collect_chapters(manuscript_dir: Path, picked: set | None) -> tuple[list, list]:
    """收集 书稿/ 下全部章节，按章号排序（无章号按文件名垫底）。"""
    chapters: list = []
    skipped: list = []
    for path in sorted(manuscript_dir.iterdir()):
        if path.suffix.lower() not in (".md", ".txt") or not path.is_file():
            continue
        num, title, body = read_chapter(path)
        if picked is not None and (num is None or num not in picked):
            skipped.append(path.name)
            continue
        chapters.append({"num": num, "title": title, "body": body, "path": path})
    chapters.sort(key=lambda c: (c["num"] is None, c["num"] or 0, c["path"].name))
    return chapters, skipped


def build_txt(chapters: list) -> str:
    parts = []
    for ch in chapters:
        parts.append(f"{ch['title']}\n\n{ch['body']}".strip())
    return "\n\n".join(parts) + "\n"


def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def export(project: str, out: str | None = None, range_spec: str | None = None,
           encoding: str = "utf-8-sig", dry_run: bool = False) -> int:
    root = Path(project).expanduser()
    manuscript = root / "书稿"
    if not manuscript.is_dir():
        print(f"[✗] 未找到 书稿/ 目录：{root.resolve()}")
        return 2
    picked = parse_range(range_spec) if range_spec else None
    chapters, skipped = collect_chapters(manuscript, picked)
    if not chapters:
        print("[✗] 书稿/ 中没有可导出的章节（.md/.txt），或 --range 未命中任何章")
        return 2

    if out:
        out_path = Path(out)
    else:
        out_path = root / "导出" / f"{root.resolve().name}_作家助手.txt"

    total = sum(count_chars(ch["body"]) for ch in chapters)
    unnamed = [c for c in chapters if c["num"] is None]
    dup = {n for c in chapters if (n := c["num"]) is not None
           and sum(1 for x in chapters if x["num"] == n) > 1}
    if dry_run:
        print(f"[i] dry-run：不写文件。将导出 {len(chapters)} 章 / 约 {total} 字 → {out_path}")
        return 0
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(build_txt(chapters), encoding=encoding)
    except OSError as exc:
        print(f"[✗] 写出失败：{exc}")
        return 1
    print(f"[✓] 已导出 {len(chapters)} 章 / {total} 字（去空白）→ {out_path}")
    print(f"[i] 编码 {encoding}；章节标题独占一行，作家助手「本地导入」可直接识别拆分")
    if skipped:
        print(f"[i] --range 未命中跳过 {len(skipped)} 个文件：{('、'.join(skipped[:5]))}{' 等' if len(skipped) > 5 else ''}")
    if unnamed:
        print(f"[!] {len(unnamed)} 个文件未解析出章号，已按文件名顺序垫底：{('、'.join(c['path'].name for c in unnamed[:5]))}")
    if dup:
        print(f"[!] 章号重复：{('、'.join(str(n) for n in sorted(dup)))}，请检查书稿命名")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="合并 书稿/ 为作家助手「本地导入」可用的单文件 txt（只读书稿，唯一写入是导出 txt）")
    ap.add_argument("project", nargs="?", default=".", help="小说项目根目录（默认当前目录）")
    ap.add_argument("--out", default=None, help="输出 txt 路径（默认 <项目根>/导出/<书名>_作家助手.txt）")
    ap.add_argument("--range", default=None, help="章号筛选，如 1-50 或 1,3,5-8")
    ap.add_argument("--encoding", default="utf-8-sig", choices=ENCODINGS,
                    help="输出编码（默认 utf-8-sig，带 BOM 防止 Windows 乱码）")
    ap.add_argument("--dry-run", action="store_true", help="只预览章数与输出路径，不写文件")
    args = ap.parse_args()
    return export(args.project, out=args.out, range_spec=args.range,
                  encoding=args.encoding, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
