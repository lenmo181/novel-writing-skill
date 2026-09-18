# -*- coding: utf-8 -*-
"""
check_chapter.py — 网络小说创作技能 v6.0 章节机械校验脚本
用法: python check_chapter.py <章节文件.md|txt> [--min 2500] [--max 3000]
只做机器可判定的校验（19项中的前7项），语义类校验仍由 AI 对照 mind/ 档案执行。
退出码: 0=通过, 1=未通过
"""
import argparse
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 可计数字符：汉字 + 中文标点（含弯引号、省略号、破折号）
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"      # 汉字
    "\u3000-\u303f"                     # CJK 标点（，。、《》「」等）
    "\uff00-\uffef"                     # 全角标点
    "\u2018\u2019\u201c\u201d\u2014\u2026]"  # 弯引号/破折号/省略号
)

DIALOGUE_SPAN = re.compile("[\u201c\u2018]([^\u201c\u2018\u201d\u2019]*)[\u201d\u2019]")

A_LEVEL = [
    "萦绕", "宛如", "仿佛", "如同", "犹如", "好比", "斑驳", "勾勒", "氤氲", "缱绻",
    "旖旎", "呢喃", "辗转反侧", "惴惴不安", "蹙眉", "噗嗤", "嫣然", "莞尔",
    "顾盼生辉", "明眸皓齿", "冰清玉洁", "倾国倾城", "沉鱼落雁", "闭月羞花",
    "纤尘不染", "不染尘埃", "恍若隔世", "如梦似幻", "如诗如画", "心旷神怡",
    "沁人心脾", "荡气回肠", "扣人心弦", "引人入胜", "令人窒息", "难以言喻",
    "无法用言语形容", "不可名状", "难以置信", "不可思议", "匪夷所思",
    "瞠目结舌", "目瞪口呆", "哑口无言",
]

B_LEVEL = [
    "深邃", "凝视", "凝望", "注视", "扫视", "瞥见", "捕捉", "涌现", "浮现",
    "弥漫", "笼罩", "蔓延", "充斥", "充盈", "饱满", "丰盈", "浓郁", "浓烈",
    "强烈", "猛烈", "剧烈", "急剧", "骤然", "猛然", "忽然", "突然", "陡然",
    "蓦然", "倏然", "霍然", "顿然", "戛然",
]

TITLE_RE = re.compile(r"^\s*第[0-9零一二三四五六七八九十百千万]{1,7}[章节回]")
SKIP_LINE_RE = re.compile(r"^\s*(#[^#]|>|```|\||---+|===+|\*{3,})")
MARKER_RE = re.compile(r"【[^】]*(?:段完成|累计|对话约|全章对话|广告位)[^】]*】")


def load_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def body_lines(text):
    """剔除章节标题、分隔线、统计标记行，保留纯正文行。"""
    kept = []
    dropped = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if TITLE_RE.match(line):
            dropped.append("章节标题: " + line.strip()[:30])
            continue
        if SKIP_LINE_RE.match(line):
            dropped.append("格式行: " + line.strip()[:30])
            continue
        kept.append(MARKER_RE.sub("", line))
    return kept, dropped


def count_chars(s):
    return len(COUNTABLE.findall(s))


def check(path, wmin, wmax):
    text = load_text(path)
    lines, dropped = body_lines(text)
    body = "\n".join(lines)
    failures, warnings = [], []

    # 1. 字数
    total = count_chars(body)
    if total < wmin:
        failures.append(f"字数 {total} < 下限 {wmin}")
    elif total > wmax:
        failures.append(f"字数 {total} > 上限 {wmax}")
    else:
        print(f"[✓] 字数 = {total}（区间 {wmin}-{wmax}）")

    # 2. 对话占比
    dialog_chars = sum(count_chars(m) for m in DIALOGUE_SPAN.findall(body))
    ratio = dialog_chars / total * 100 if total else 0
    if ratio < 40:
        failures.append(f"对话占比 {ratio:.1f}% < 40%（对话约 {dialog_chars} 字）")
    else:
        print(f"[✓] 对话占比 = {ratio:.1f}%（对话约 {dialog_chars} 字）")

    # 3. A级禁言词
    a_hits = [(w, body.count(w)) for w in A_LEVEL if w in body]
    if a_hits:
        failures.append("A级禁言词出现: " + "、".join(f"{w}×{n}" for w, n in a_hits))
    else:
        print("[✓] A级禁言词 = 0")

    # 4. B级限制词（超3次仅警告）
    b_hits = [(w, body.count(w)) for w in B_LEVEL if body.count(w) > 3]
    if b_hits:
        warnings.append("B级限制词超频(>3): " + "、".join(f"{w}×{n}" for w, n in b_hits))
    else:
        print("[✓] B级限制词均在限额内")

    # 5. 破折号
    dash = body.count("——")
    if dash > 2:
        failures.append(f"破折号——出现 {dash} 次 > 上限 2")
    else:
        print(f"[✓] 破折号—— = {dash} 次")

    # 6. 引号规范
    straight = sum(body.count(c) for c in "\"'")
    corner = sum(body.count(c) for c in "「」『』")
    if straight or corner:
        failures.append(
            f"引号违规：半角直引号×{straight}，直角引号×{corner}（必须用弯引号）"
        )
    else:
        print("[✓] 引号规范（中文弯引号）")

    # 7. 格式残留
    if dropped:
        sample = "；".join(dropped[:3])
        if any(d.startswith("格式行") for d in dropped):
            failures.append(f"检测到格式残留（{len(dropped)}行被剔除，如: {sample}）")
        else:
            print(f"[i] 剔除标题行 {len(dropped)} 个（不计字数）")
    quotes_balanced = body.count("\u201c") == body.count("\u201d")
    if not quotes_balanced:
        warnings.append(
            f"弯引号不配对：左 {body.count(chr(0x201c))} 个 / 右 {body.count(chr(0x201d))} 个"
        )
    if not failures and quotes_balanced:
        print("[✓] 无格式残留")

    print("-" * 46)
    for w in warnings:
        print(f"[!] 警告: {w}")
    for f in failures:
        print(f"[✗] 未通过: {f}")
    print("-" * 46)
    if failures:
        print(f"结论：校验未通过（{len(failures)} 项硬伤，{len(warnings)} 项警告）")
        print(f"摘要：字数={total} 对话占比={ratio:.1f}% —— 禁止交付，先修复再跑本脚本")
        return 1
    print(f"结论：机械校验全部通过 ✓（另有 {len(warnings)} 项警告需人工过目）")
    print(f"摘要：字数={total} 对话占比={ratio:.1f}% A级=0")
    return 0


def main():
    ap = argparse.ArgumentParser(description="章节机械校验")
    ap.add_argument("file")
    ap.add_argument("--min", type=int, default=2500)
    ap.add_argument("--max", type=int, default=3000)
    args = ap.parse_args()
    sys.exit(check(args.file, args.min, args.max))


if __name__ == "__main__":
    main()
