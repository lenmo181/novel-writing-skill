# -*- coding: utf-8 -*-
"""
conflict_score.py — 章节冲突值计算器（v7.4）
公式: 冲突值 = 基础分(默认1) + Σ(因子权重 × 触发次数)

因子权重（与 references/节奏与结构.md、references/常量表.md 1:1）:
    core_state_change   核心角色状态根本性改变          +8
    tier1_foreshadow    Tier-1 战略级伏笔回收或埋设      +8
    tier2_foreshadow    Tier-2 战役级伏笔回收或埋设      +5
    breakthrough        破格事件                        +5
    entity_change       重要实体（组织/物品）状态改变    +3
    core_character      核心角色参与（每位）            +2

星级映射: <5 ★☆☆☆☆ | 5-7 ★★☆☆☆ | 8-11 ★★★☆☆ | 12-15 ★★★★☆(峰值) | ≥16 ★★★★★(核心峰值)

用法:
    python conflict_score.py --demo                      # 跑手册里的三个算例
    python conflict_score.py --json chapters.json        # 批量算章（见 --help 的 JSON 格式）
    python conflict_score.py --json x.json --base 2      # 自定义基础分

JSON 格式（两种因子写法都支持）:
    {"chapters": [
      {"chapter": 12, "title": "落水",
       "factors": ["core_character", "entity_change", "core_character"]},
      {"chapter": 13, "title": "退场",
       "factors": {"core_state_change": 1, "tier2_foreshadow": 1, "core_character": 2}}
    ]}

护栏: 冲突值只用于事后标注与体检，严禁为提分而新增死亡/暴力/黑化事件；
      一切事件仍受 SKILL.md《平台审核红线》约束。
退出码: 0=正常, 1=输入错误
"""
import argparse
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DEFAULT = 1
PEAK_MIN = 12  # 峰值线：★★★★☆ 及以上

WEIGHTS = [
    ("core_state_change", "核心角色状态根本性改变", 8),
    ("tier1_foreshadow", "Tier-1 战略级伏笔回收/埋设", 8),
    ("tier2_foreshadow", "Tier-2 战役级伏笔回收/埋设", 5),
    ("breakthrough", "破格事件", 5),
    ("entity_change", "重要实体（组织/物品）状态改变", 3),
    ("core_character", "核心角色参与（每位）", 2),
]
WEIGHT_MAP = {k: w for k, _, w in WEIGHTS}
LABEL_MAP = {k: lbl for k, lbl, _ in WEIGHTS}

STARS = [(5, "★☆☆☆☆", "日常"), (8, "★★☆☆☆", "推进"), (12, "★★★☆☆", "节点"),
         (16, "★★★★☆", "峰值"), (10 ** 9, "★★★★★", "核心峰值")]


def star_of(score):
    for upper, stars, name in STARS:
        if score < upper:
            return stars, name
    return "★★★★★", "核心峰值"


def is_peak(score):
    return score >= PEAK_MIN


def normalize_factors(factors):
    """list[str] 或 dict[str,int] → [(factor_key, count)]"""
    if factors is None:
        return []
    items = []
    if isinstance(factors, dict):
        for k, v in factors.items():
            items.append((k, int(v)))
        return items
    counts = {}
    for k in factors:
        if isinstance(k, (list, tuple)) and len(k) == 2 and isinstance(k[1], int):
            counts[k[0]] = counts.get(k[0], 0) + k[1]  # 已展开的 (因子, 次数)
        else:
            counts[k] = counts.get(k, 0) + 1
    return list(counts.items())


def compute(factors, base=BASE_DEFAULT):
    total = base
    detail = []
    for k, n in factors:
        if k not in WEIGHT_MAP:
            raise KeyError(k)
        gain = WEIGHT_MAP[k] * n
        total += gain
        detail.append((LABEL_MAP[k], n, WEIGHT_MAP[k], gain))
    return total, detail


def render(chapter_no, title, factors, base=BASE_DEFAULT):
    total, detail = compute(normalize_factors(factors), base)
    stars, name = star_of(total)
    head = f"第{chapter_no}章" if chapter_no is not None else "(未编号)"
    if title:
        head += f"《{title}》"
    print(f"{head}  基础分 {base}")
    for lbl, n, w, gain in detail:
        print(f"    + {lbl} ×{n}（权重 {w}） = +{gain}")
    print(f"  冲突值 = {total} → {stars} {name}" + ("  【峰值】" if is_peak(total) else ""))
    if is_peak(total):
        print("  提醒：峰值章前后各 2 章内不得排「缓冲-对话」；同卷内不宜再出同量级章")
    return total


def check_peak_spacing(results, gap=4):
    """峰值间距：两个峰值章相隔 < gap 章 → 提醒"""
    peaks = [no for no, score in results if is_peak(score)]
    warn = []
    for a, b in zip(peaks, peaks[1:]):
        if b - a < gap:
            warn.append((a, b))
    return warn


def demo():
    print("=" * 60)
    print("算例一：日常缓冲章（茶馆递线索）——主角 + 一位配角，无状态变更")
    for k, _, w in WEIGHTS:
        print(f"  权重表: {LABEL_MAP[k]:<24} +{w}")
    print("-" * 60)
    s1 = render(1, "茶馆", ["core_character"])

    print("-" * 60)
    print("算例二：单元内小高潮（擂台胜宿敌 + 信物易主 + 敌方核心退场）")
    s2 = render(2, "擂台", ["core_state_change", "entity_change",
                            "core_character", "core_character"])
    print("  变体：本场只留『胜擂 + 信物易主』（宿敌退场另排一章）")
    s2b = render(2, "擂台(拆分版)", ["entity_change",
                                     "core_character", "core_character"])

    print("-" * 60)
    print("算例三：卷末核心峰值（突破 + T1 伏笔回收 + 破格 + 4 位核心角色）")
    s3 = render(3, "卷末", ["core_state_change", "tier1_foreshadow", "breakthrough",
                            "core_character", "core_character", "core_character",
                            "core_character"])

    print("=" * 60)
    print(f"三算例分值: {s1} / {s2} / {s2b} / {s3}"
          f" → 星级 {star_of(s1)[0]} / {star_of(s2)[0]} / {star_of(s2b)[0]} / {star_of(s3)[0]}")
    print("护栏：冲突值只用于事后标注与体检，严禁为提分新增死亡/暴力/黑化事件；")
    print("      一切事件仍受《平台审核红线》约束。冲突值 ≠ 爽点强度，两者不可互推。")
    return 0


def run_json(path, base):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[✗] 无法读取 JSON：{e}")
        return 1
    if isinstance(data, list):
        chapters = data
    elif isinstance(data, dict):
        chapters = data.get("chapters", [])
    else:
        chapters = []
    if not isinstance(chapters, list) or not chapters:
        print("[✗] JSON 中没有 chapters 数组，也没有章节列表")
        return 1
    results, peak_note = [], []
    for ch in chapters:
        if not isinstance(ch, dict):
            print("[✗] JSON 章节项必须是对象")
            return 1
        no = ch.get("chapter")
        if no is not None and (isinstance(no, bool) or not isinstance(no, int)):
            # v7.25 修复：字符串/列表章号此前在 render 后的峰值过滤才炸 TypeError，
            # 现在入口处给受控输入错误
            print(f"[✗] chapter 字段必须是整数（或省略），收到 {type(no).__name__}：{no!r}")
            return 1
        try:
            total = render(no, ch.get("title"), ch.get("factors"), base)
        except KeyError as e:
            print(f"[✗] 未知因子名 {e}（第{no}章）。合法因子: "
                  + "、".join(k for k, _, _ in WEIGHTS))
            return 1
        except (TypeError, ValueError) as e:
            print(f"[✗] 第{no}章因子格式错误：{e}")
            return 1
        results.append((no if no is not None else -1, total))
        if is_peak(total):
            peak_note.append(no)
    numbered = [(n, s) for n, s in results if n > 0]
    warn = check_peak_spacing(numbered)
    print("-" * 60)
    if peak_note:
        print("峰值章: " + "、".join(f"第{n}章" for n in peak_note if n) +
              "——前后各 2 章内不得排「缓冲-对话」")
    if warn:
        print("[!] 峰值间距过近（<4 章）: " +
              "；".join(f"第{a}章 与 第{b}章" for a, b in warn) + "——峰值通胀，读者脱敏")
    if not warn and not peak_note:
        print("[i] 本批无峰值章（分值 ≥12）。日常章分值低不是缺陷，勿为提分加事件。")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="章节冲突值计算器（权重表见 references/节奏与结构.md，1:1 同步）",
        epilog="护栏：仅用于事后标注与体检，严禁为提分新增死亡/暴力/黑化事件。")
    ap.add_argument("--demo", action="store_true", help="输出权重表与三个算例")
    ap.add_argument("--json", metavar="FILE", help="批量计算：读取章章节目的 JSON")
    ap.add_argument("--base", type=int, default=BASE_DEFAULT, help="基础分（默认 1）")
    args = ap.parse_args()

    if args.demo:
        sys.exit(demo())
    if args.json:
        sys.exit(run_json(args.json, args.base))
    ap.print_help()
    print("\n提示：先跑 --demo 看权重表与算例；批量计算请用 --json <file>。")
    sys.exit(0)


if __name__ == "__main__":
    main()
