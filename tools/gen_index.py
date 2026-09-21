# -*- coding: utf-8 -*-
"""
gen_index.py — 扫描 书稿/ 生成 mind/章节目录.md（v7.4）
用法: python gen_index.py [项目根目录] [--dry-run]

列: 章号 | 标题 | 字数 | 节奏类型 | 校验结果 | 完成日期
    （旧表中存在的额外列，如「冲突值」「对话占比」，会被保留并追加在末尾）

合并策略（核心，不可简化）:
    读旧表 → 按章号合并 → 只补缺省行
    · 已存在的「校验结果」「完成日期」等单元格值一律原样保留，绝不覆盖
    · 新章号才新增行；旧表出现而书稿已删的章号保留不动（只提示）
    · 末尾「当前进度」行的进度数字按书稿刷新，附加信息（如「待办：…」）原样保留；
      旧进度章号大于书稿实际最大章号时整行保留旧值并提示

字数口径复用 check_chapter.count_chars（纯正文，排除章节标题行与格式行）。
退出码: 0=正常, 1=输入错误（书稿/ 不存在或无章节文件）
"""
import argparse
import os
import re
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.dont_write_bytecode = True  # 复用 check_chapter 时不生成 __pycache__ 残留
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_chapter  # noqa: E402  （复用字数口径与正文行切分）

STD_COLS = ["章号", "标题", "字数", "节奏类型", "校验结果", "完成日期"]

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

CHAP_FILE_RE = re.compile(
    r"^第\s*([0-9]{1,6}|[零一二三四五六七八九十百千万两]{1,8})\s*[章节回]"
    r"(?:\s*[_\-\u2014\s]\s*(.*?))?\s*$")


def cn_to_int(s):
    """中文数字转整数（覆盖 1-99999 的常见写法）。"""
    total, section, number = 0, 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section, number = 0, 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            return None
    return total + section + number


def parse_chapter_name(filename):
    """'第001章_落水.md' -> (1, '落水')；解析失败返回 (None, None)。"""
    stem = os.path.splitext(filename)[0]
    m = CHAP_FILE_RE.match(stem)
    if not m:
        m = CHAP_FILE_RE.match(stem.replace("_", " ").split(" ")[0])
        if not m:
            return None, None
    raw, title = m.group(1), (m.group(2) or "").strip(" _-—")
    if raw.isdigit():
        num = int(raw)
    else:
        num = cn_to_int(raw)
    return num, (title or None)


def read_body_chars(path):
    """纯正文字数（与 check_chapter 同口径）。"""
    text = check_chapter.load_text(path)
    lines, _ = check_chapter.body_lines(text)
    return check_chapter.count_chars("\n".join(lines))


def parse_old_index(path):
    """返回 (header, rows, progress)。rows: {章号: {列名: 值}}"""
    header, rows, progress = None, {}, None
    if not os.path.isfile(path):
        return header, rows, progress
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("当前进度"):
                progress = s
            if "|" not in s:
                continue
            cells = [c.strip().replace("**", "") for c in s.strip("|").split("|")]
            if all(c == "" or set(c) <= set("-: ") for c in cells):
                continue  # 分隔行
            if header is None:
                if "章号" in cells:
                    header = cells
                continue
            if re.fullmatch(r"\d+", cells[0]):
                rows[int(cells[0])] = dict(zip(header, cells))
    return header, rows, progress


def collect_chapters(book_dir):
    out = []
    for name in sorted(os.listdir(book_dir)):
        if not name.lower().endswith((".md", ".txt")):
            continue
        num, title = parse_chapter_name(name)
        if num is None:
            print(f"[i] 跳过非章节文件: {name}")
            continue
        out.append((num, name, title))
    out.sort(key=lambda x: x[0])
    return out


def build(project, dry_run=False):
    book_dir = os.path.join(project, "书稿")
    mind_dir = os.path.join(project, "mind")
    index_path = os.path.join(mind_dir, "章节目录.md")

    if not os.path.isdir(book_dir):
        print(f"[✗] 未找到书稿目录: {book_dir}")
        return 1
    chapters = collect_chapters(book_dir)
    if not chapters:
        print(f"[✗] 书稿目录下没有可识别的章节文件: {book_dir}")
        return 1

    old_header, old_rows, old_progress = parse_old_index(index_path)
    extra_cols = []
    if old_header:
        extra_cols = [c for c in old_header if c not in STD_COLS]

    cols = STD_COLS + extra_cols
    rows, added, kept = [], 0, 0
    seen = set()
    for num, fname, title in chapters:
        seen.add(num)
        path = os.path.join(book_dir, fname)
        old = old_rows.get(num, {})
        if old:
            kept += 1
        else:
            added += 1
        chars = read_body_chars(path)
        done_date = old.get("完成日期") or datetime.fromtimestamp(
            os.path.getmtime(path)).strftime("%Y-%m-%d")
        row = {
            "章号": str(num),
            "标题": old.get("标题") or title or "",
            "字数": str(chars),
            "节奏类型": old.get("节奏类型", ""),
            "校验结果": old.get("校验结果", ""),
            "完成日期": done_date,
        }
        for c in extra_cols:
            row[c] = old.get(c, "")
        rows.append(row)

    vanished = sorted(set(old_rows) - seen)
    if vanished:
        print(f"[!] 旧表中有 {len(vanished)} 个章号在 书稿/ 中找不到对应文件，保留旧行: "
              + "、".join(f"第{n}章" for n in vanished[:10])
              + ("…" if len(vanished) > 10 else ""))
        for num in vanished:
            old = old_rows[num]
            row = {c: old.get(c, "") for c in cols}
            row["章号"] = str(num)
            rows.append(row)
        rows.sort(key=lambda r: int(r["章号"]))

    max_num = max(n for n, _, _ in chapters)
    # 进度行是派生数据：进度数字按最新章节数刷新；行内附加信息（如「待办：…」）原样保留
    # （v7.25 修复：此前重建会吃掉「；待办：…」尾巴）。仅当旧进度记录的章号**大于**书稿实际
    # 最大章号时整行保留旧值（说明有章未落盘）并提示。
    old_done = None
    if old_progress:
        m = re.search(r"已完成至第\s*(\d+)\s*章", old_progress)
        if m:
            old_done = int(m.group(1))
    if old_done is not None and old_done > max_num:
        print(f"[!] 旧进度行记录已完成至第{old_done}章，但 书稿/ 只到第{max_num}章——保留旧进度行，请人工核对")
        progress = old_progress
    else:
        progress = f"当前进度：已完成至第{max_num}章，下一章为第{max_num + 1}章"
        if old_progress:
            m2 = re.search(r"下一章为第\s*\d+\s*章", old_progress)
            if m2:
                extra = old_progress[m2.end():].strip()
                if extra:
                    progress += extra if extra.startswith(("；", ";")) else "；" + extra

    lines = ["# 章节目录", "",
             "| " + " | ".join(cols) + " |",
             "|" + "|".join(["------"] * len(cols)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row.get(c, "") for c in cols) + " |")
    lines += ["", progress, ""]

    print(f"[i] 章节文件 {len(chapters)} 个 | 旧表命中 {kept} 行 | 新增 {added} 行"
          f" | 保留额外列: {'、'.join(extra_cols) if extra_cols else '无'}")
    for row in rows:
        if row["校验结果"]:
            print(f"[i] 保留既有校验结果: 第{row['章号']}章 = {row['校验结果']}")
    if dry_run:
        print("[i] --dry-run：未写入文件。预览如下")
        print("\n".join(lines[:8]) + "\n…")
        return 0
    os.makedirs(mind_dir, exist_ok=True)
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"[✓] 已写入 {index_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="扫描 书稿/ 生成 mind/章节目录.md（读旧表合并，不覆盖既有值）")
    ap.add_argument("project", nargs="?", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--dry-run", action="store_true", help="只预览不写文件")
    args = ap.parse_args()
    sys.exit(build(os.path.abspath(args.project), args.dry_run))


if __name__ == "__main__":
    main()
