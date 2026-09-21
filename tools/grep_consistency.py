# -*- coding: utf-8 -*-
"""
grep_consistency.py — mind/ 档案与正文的四类硬矛盾告警（v7.9，轻量·仅告警）
用法: python grep_consistency.py [项目根目录] [--limit 200]

查四类机器可判定的硬矛盾（不做语义推断，只做字面命中）:
    A 已亡/退场实体再度出场 —— 角色状态快照标「已亡/退场」的实体，在其「最后出场」章之后
      的正文里再次出现（名字或别名）
    B 伤势/状态与前文快照冲突 —— 快照状态含伤情标记，而正文同句出现「痊愈/伤愈/无碍」类表述
    C 同一物品双持有人 —— 快照「持有」字段中同一件物品被两个及以上角色同时持有
    D 剧情推进力告警（v7.9 反打圈）—— mind/章节目录.md 的「节奏类型」列：
      同一节奏类型连续 ≥3 章，或任意「缓冲-」型合计连续 ≥4 章 → 打圈风险
      （数据源是章纲/目录标注，检测的是排纲层打圈；正文层打圈靠第30项语义校验）

数据源:
    mind/角色状态快照.md（## 角色名 + “- 字段：值” 行）
    mind/章节目录.md（Markdown 表格「节奏类型」列，gen_index.py 生成）
    书稿/*.md（按章号排序，只扫描「最后出场」之后的章节，上限 --limit 章）

边界声明: 未提供的档案不推断；扫描有章数上限，输出里会写清扫描范围。
退出码: **恒为 0**（只告警，交人工判断；无告警也返回 0）
"""
import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEATH_MARKS = ("已亡", "已死", "死亡", "身亡", "阵亡", "殒命", "战死", "已殁",
               "退场", "已退出", "离场（不再回归）", "已下线")
INJURY_MARKS = ("重伤", "受伤", "断腿", "断臂", "骨折", "中毒", "昏迷", "濒死",
                "残废", "卧床", "伤重")
HEAL_MARKS = ("痊愈", "伤愈", "复原", "康复", "已无大碍", "毫发无伤", "完好如初",
              "生龙活虎", "健步如飞", "行动自如")

CHAP_RE = re.compile(r"^第\s*([0-9]{1,6})\s*[章节回]")
FIELD_RE = re.compile(r"^[-*·]?\s*([\u4e00-\u9fffA-Za-z]{1,6})\s*[：:]\s*(.*)$")
NAME_HEAD_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
ITEM_SPLIT_RE = re.compile(r"[、，,;；/／|]|和|与")
ITEM_STOP = {"无", "空", "暂无", "没有", "—", "-", "", "（无）", "(无)"}


def load(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_snapshot(path):
    """→ {角色名: {字段: 值, '_line': 行号}}"""
    chars, cur = {}, None
    if not os.path.isfile(path):
        return chars
    for lineno, line in enumerate(load(path).splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        m = NAME_HEAD_RE.match(s)
        if m:
            cur = m.group(1).strip(" *#")
            if cur and cur not in ("角色状态快照", "角色名"):
                chars.setdefault(cur, {"_line": lineno})
            continue
        if cur is None:
            continue
        fm = FIELD_RE.match(s)
        if fm:
            chars[cur][fm.group(1)] = fm.group(2).strip()
    return chars


def parse_aliases(value):
    if not value:
        return []
    v = value.strip()
    if v in ITEM_STOP or v.startswith("无"):
        return []
    return [x.strip() for x in re.split(r"[、，,/\u3001]", v) if x.strip() and x.strip() not in ITEM_STOP]


def parse_items(value):
    if not value:
        return []
    if value.strip() in ITEM_STOP or value.strip().startswith("无"):
        return []
    out = []
    for raw in ITEM_SPLIT_RE.split(value):
        item = (raw or "").strip().strip("（）()【】")
        if 1 < len(item) <= 12 and item not in ITEM_STOP and not item.isdigit():
            out.append(item)
    return out


def parse_last_chapter(value):
    if not value:
        return None
    m = re.search(r"第\s*([0-9]{1,6})\s*章", value)
    return int(m.group(1)) if m else None


def iter_chapters(book_dir):
    out = []
    if not os.path.isdir(book_dir):
        return out
    for name in sorted(os.listdir(book_dir)):
        if not name.lower().endswith((".md", ".txt")):
            continue
        m = CHAP_RE.match(os.path.splitext(name)[0].strip())
        if m:
            out.append((int(m.group(1)), os.path.join(book_dir, name)))
    out.sort(key=lambda x: x[0])
    return out


def scan_rhythm_stall(project):
    """D 类：章节目录「节奏类型」列的连续性检测（排纲层打圈告警）。"""
    path = os.path.join(project, "mind", "章节目录.md")
    if not os.path.isfile(path):
        return []
    header, seq = None, []
    for line in load(path).splitlines():
        s = line.strip()
        if "|" not in s:
            continue
        cells = [c.strip().replace("**", "") for c in s.strip("|").split("|")]
        if all(c == "" or set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            if "节奏类型" in cells:
                header = cells
            continue
        if re.fullmatch(r"\d+", cells[0]):
            idx = header.index("节奏类型")
            seq.append((int(cells[0]), cells[idx] if idx < len(cells) else ""))
    issues, i = [], 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1][1] == seq[i][1]:
            j += 1
        run = j - i + 1
        kind = seq[i][1] or "（未标注）"
        if run >= 3:
            chs = f"第{seq[i][0]}-第{seq[j][0]}章" if run > 1 else f"第{seq[i][0]}章"
            issues.append((
                "D", "中", f"mind/章节目录.md（{chs}）",
                f"节奏类型「{kind}」连续 {run} 章",
                "排纲层打圈风险：注入新信息/新人物/新限制或时间跳跃破圈（见《剧情推进力铁律》）"))
        i = j + 1
    # 任意缓冲型合计连续 ≥4 章
    run_buf, start = 0, None
    for k, (num, kind) in enumerate(seq + [(-1, "#END#")]):
        if kind.startswith("缓冲"):
            if run_buf == 0:
                start = num
            run_buf += 1
            continue
        if run_buf >= 4:
            issues.append((
                "D", "中", f"mind/章节目录.md（第{start}章起）",
                f"「缓冲-」型合计连续 {run_buf} 章",
                "连续缓冲超限：至少 1 章换主线/峰值型，否则读者追读感会崩"))
        run_buf = 0
    return issues


def scan(project, limit=200):
    project = os.path.abspath(project)
    snap_path = os.path.join(project, "mind", "角色状态快照.md")
    book_dir = os.path.join(project, "书稿")
    issues = scan_rhythm_stall(project)

    if not os.path.isfile(snap_path):
        print(f"[i] 未找到 {snap_path}，无法执行 A/B/C 三类检测（不推断缺失档案）")
        return issues
    chars = parse_snapshot(snap_path)
    if not chars:
        print(f"[i] {snap_path} 中未解析到角色条目（格式需为 '## 角色名' + '- 字段：值'）")
        return issues

    chapters = iter_chapters(book_dir)
    scanned = []
    if chapters:
        truncated = len(chapters) > limit
        scanned = chapters[-limit:] if truncated else chapters
        print(f"[i] 扫描范围：第{scanned[0][0]}-{scanned[-1][0]}章（共 {len(scanned)} 章）"
              + (f"；更早章节超出上限 {limit} 章未扫描" if truncated else ""))

    all_names = set(chars.keys())
    for name, fields in chars.items():
        for alias in parse_aliases(fields.get("别名", "")):
            all_names.add(alias)

    # ── A 已亡/退场实体再度出场 ──
    for name, fields in sorted(chars.items()):
        status = fields.get("状态", "") + fields.get("伤势", "")
        if not any(mark in status for mark in DEATH_MARKS):
            continue
        last = parse_last_chapter(fields.get("最后出场", ""))
        names = [name] + parse_aliases(fields.get("别名", ""))
        for num, path in scanned:
            if last is not None and num <= last:
                continue
            for lineno, line in enumerate(load(path).splitlines(), 1):
                if any(n and n in line for n in names):
                    issues.append((
                        "A", "高", f"{os.path.relpath(path, project)}:{lineno}",
                        f"标记「{status}」的实体「{name}」（最后出场第{last}章）在第{num}章正文中再次出现",
                        "确认是回忆/幻觉/替身/同名，否则属吃书"))
                    break

    # ── B 伤势/状态与前文快照冲突 ──
    for name, fields in sorted(chars.items()):
        status = fields.get("状态", "") + fields.get("伤势", "")
        hurt = [m for m in INJURY_MARKS if m in status]
        if not hurt:
            continue
        names = [name] + parse_aliases(fields.get("别名", ""))
        reported = False
        for num, path in scanned:
            if reported:
                break
            for lineno, line in enumerate(load(path).splitlines(), 1):
                if not any(n and n in line for n in names):
                    continue
                hit = [m for m in HEAL_MARKS if m in line]
                if hit:
                    issues.append((
                        "B", "中", f"{os.path.relpath(path, project)}:{lineno}",
                        f"快照中「{name}」状态为「{fields.get('状态', '')}」"
                        f"（伤情标记：{'、'.join(hurt)}），第{num}章正文出现「{hit[0]}」",
                        "确认是否有疗伤情节支撑；无支撑则改为未愈"))
                    reported = True
                    break

    # ── C 同一物品双持有人 ──
    holders = {}
    for name, fields in chars.items():
        for item in parse_items(fields.get("持有", "")):
            holders.setdefault(item, []).append((name, fields.get("_line", 0)))
    for item, who in sorted(holders.items()):
        uniq = sorted({n for n, _ in who})
        if len(uniq) >= 2:
            loc = "、".join(f"{os.path.relpath(snap_path, project)}:{ln}" for _, ln in who)
            issues.append((
                "C", "中", loc,
                f"物品「{item}」同时被 {'、'.join(uniq)} 持有",
                "确认是否分身/复制品，否则改为单一持有人"))

    # ── D 剧情推进力（排纲层打圈）已在 scan() 开头扫描（v7.25 修复重复告警）──
    return issues


def main():
    ap = argparse.ArgumentParser(
        description="mind/ 档案与正文的四类硬矛盾告警（A已亡再出场 / B伤势冲突 / C物品双持有人 / D推进力打圈）")
    ap.add_argument("project", nargs="?", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--limit", type=int, default=200, help="最多回溯扫描的章数（默认200）")
    args = ap.parse_args()

    issues = scan(args.project, args.limit)
    print("-" * 60)
    if not issues:
        print("[✓] 未发现四类硬矛盾（A已亡再出场 / B伤势冲突 / C物品双持有人 / D推进力打圈）")
        print("说明：本脚本只做字面命中，不判语义；未命中不代表没有问题。")
        sys.exit(0)
    for kind, level, loc, desc, fix in issues:
        print(f"[告警-{kind}/{level}] {loc} | {desc} | 建议：{fix}")
    print("-" * 60)
    print(f"合计 {len(issues)} 条告警（仅告警，退出码恒为 0，交人工判断）")
    sys.exit(0)


if __name__ == "__main__":
    main()
