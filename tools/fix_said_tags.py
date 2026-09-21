# -*- coding: utf-8 -*-
"""
fix_said_tags.py — 「他/她说：」类光杆引导批量修复工具（v7.17，弯引号流专用）
用法:
  python fix_said_tags.py <书稿目录> [--dry-run] [--no-backup] [--walls] [--meta]
  --dry-run   只统计与抽样展示，不写文件
  --no-backup 跳过备份（默认备份到 <目录>/../mind/大修备份/修复原稿/）
  --walls     同时把>140字的无引号长段在句界拆分（文字墙硬卡）
  --meta      同时删除元信息残留行（章节更新时间/字数统计等）
只处理中文弯引号（“”）书稿；无引号对白流（千门系）禁止使用本工具——其"他说，"为风格合法对话标记。
修复规则（对齐 SKILL.md 对话归位六式）:
  1) 光杆前缀「他说，“Q”」「他说：“Q”」→ 删标签留引号（引号后的正文原样保留，v7.25 修复）
  2) 带修饰语「他压低声音说，“Q”」→「他压低声音。“Q”」（说转句号，零信息损失）
  3) 独立标签行「他又说。」→ 删行（结构词又/再/接着视同光杆）；带修饰语则转动作句保留
  4) 后缀「”他说。」→ 删后缀；带修饰语「”他压低声音说道。」→「”他压低声音。」（说道转句号，修饰语保留）
备份: 默认备份到 <目录>/../mind/大修备份/修复原稿/；同名备份已存在时另存时间戳副本
      （首轮备份永不覆盖，重复修复可逐轮回滚，v7.25）
退出码: 0=完成
"""
import argparse
import glob
import os
import re
import shutil
import sys
from datetime import datetime

NL = chr(10)
STRUCT = ("又", "再", "接着", "然后")
MOD_CH = r"[^，。：”“\n的话着]"
# 行中连接处：”他说，“Q2” → ”换行“Q2”（拆成两段，热榜式裸引号）
JUNC = re.compile(r"(”)\s*([他她它])(" + MOD_CH + "{0,4}?)(说道?)([，。：]?)\s*(“)")
# 行首前缀：他说，“Q” → “Q”
SAME = re.compile(r"^([他她它])(" + MOD_CH + "{0,4}?)(说道?)([，。：]?)\s*(“[^”]*”)")
# 独立标签行
LINE_TAG = re.compile(r"^([他她它])(" + MOD_CH + "{0,4}?)(说道?)([，。：]?)$")
# 行尾后缀：……。”他说。→ 删后缀
END_TAG = re.compile(r"(”)\s*([他她它])(" + MOD_CH + "{0,4}?)(说道?)([，。：]?)\s*$")


def _beat(pron, mod):
    return f"{pron}{mod}。"


def process_line(ln, stat):
    # 行中连接处（可能多处）
    while True:
        m = JUNC.search(ln)
        if not m:
            break
        mod = m.group(3)
        if mod and mod not in STRUCT:
            repl = m.group(1) + NL + _beat(m.group(2), mod) + NL + m.group(6)
            stat[3] += 1
        else:
            repl = m.group(1) + NL + m.group(6)
            stat[0] += 1
        ln = ln[:m.start()] + repl + ln[m.end():]
    out = []
    for seg in ln.split(NL):
        s = seg.strip()
        m = SAME.match(s)
        if m:
            mod = m.group(2)
            tail = s[m.end():]  # 引号后的正文必须原样保留（v7.25 修复：此前被静默截断）
            if mod and mod not in STRUCT:
                out.append(_beat(m.group(1), mod) + m.group(5) + tail)
                stat[3] += 1
            else:
                out.append(m.group(5) + tail)
                stat[0] += 1
            continue
        m = END_TAG.search(s)
        if m:
            mod = m.group(3)
            if mod and mod not in STRUCT:
                # 带修饰语：修饰语保留为动作句（零信息损失，同规则2说转句号）
                out.append(s[:m.start(1) + 1] + m.group(2) + mod + "。")
                stat[3] += 1
            else:
                out.append(s[:m.start(1) + 1])
                stat[1] += 1
            continue
        m = LINE_TAG.match(s)
        if m:
            mod = m.group(2)
            if mod and mod not in STRUCT:
                out.append(_beat(m.group(1), mod))
                stat[3] += 1
            else:
                stat[2] += 1
            continue
        out.append(seg)
    return NL.join(out)


def process(path, dry, backup_dir, do_walls, do_meta, skip_tags=False):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    orig = text
    stat = [0, 0, 0, 0]
    out_lines = []
    for ln in text.split(NL):
        if not skip_tags and ("”" in ln or "“" in ln or LINE_TAG.match(ln.strip())):
            out_lines.append(process_line(ln, stat))
        else:
            out_lines.append(ln)
    text = NL.join(out_lines)

    n_meta = 0
    if do_meta:
        kept = []
        for ln in text.split(NL):
            if re.match(r"^\s*(?:章节更新时间|更新时间|本章字数|字数统计|总字数|发布时间)[：:]", ln):
                n_meta += 1
                continue
            kept.append(ln)
        text = NL.join(kept)

    n_wall = 0
    if do_walls:
        parts = []
        for ln in text.split(NL):
            if len(ln) > 140:
                # 句界切点必须在引号span之外（引号感知，防拆断对白）
                outside = set()
                in_q = False
                for i, ch in enumerate(ln):
                    if ch == "“":
                        in_q = True
                    elif ch == "”":
                        in_q = False
                    elif not in_q:
                        outside.add(i)
                mid = len(ln) // 2
                cuts = [m.end() for m in re.finditer(r"[。！？；]", ln)
                        if m.end() in outside and abs(m.end() - mid) <= 60]
                if cuts:
                    cut = min(cuts, key=lambda x: abs(x - mid))
                    parts.append(ln[:cut])
                    parts.append(ln[cut:])
                    n_wall += 1
                    continue
            parts.append(ln)
        text = NL.join(parts)

    changed = text != orig
    if changed and not dry:
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            dst = os.path.join(backup_dir, os.path.basename(path))
            if os.path.exists(dst):
                # 首轮备份不覆盖（v7.25）：后续每轮另存带时间戳副本，保证最初原稿可回滚
                stem, ext = os.path.splitext(dst)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                cand = f"{stem}_{ts}{ext}"
                n = 2
                while os.path.exists(cand):
                    cand = f"{stem}_{ts}_{n}{ext}"
                    n += 1
                dst = cand
            shutil.copy2(path, dst)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return stat[0], stat[1], stat[2], stat[3], n_meta, n_wall, changed


def main():
    ap = argparse.ArgumentParser(description="「他/她说」光杆引导批量修复（弯引号流专用）")
    ap.add_argument("dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--walls", action="store_true")
    ap.add_argument("--no-tags", action="store_true", dest="no_tags", help="无引号对白流专用：跳过一切说类标签修复（其「他说」为风格合法标记）")
    ap.add_argument("--meta", action="store_true")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "*.md")))
    backup_dir = None
    if not a.no_backup and not a.dry_run:
        backup_dir = os.path.normpath(os.path.join(a.dir, "..", "mind", "大修备份", "修复原稿"))
    t_same = t_suf = t_drop = t_beat = t_meta = t_wall = n_chg = 0
    for f in files:
        r = process(f, a.dry_run, backup_dir, a.walls, a.meta, skip_tags=a.no_tags)
        t_same += r[0]; t_suf += r[1]; t_drop += r[2]; t_beat += r[3]
        t_meta += r[4]; t_wall += r[5]
        if r[6]:
            n_chg += 1
    mode = "[dry-run] " if a.dry_run else ""
    print(f"{mode}扫描 {len(files)} 章，改动 {n_chg} 章")
    print(f"同行标签修复 {t_same} | 后缀删除 {t_suf} | 独立标签行删除 {t_drop} | 转动作句 {t_beat}")
    print(f"元信息行删除 {t_meta} | 长段拆分 {t_wall}")
    if backup_dir and n_chg:
        print(f"原稿备份 → {backup_dir}")


if __name__ == "__main__":
    main()
