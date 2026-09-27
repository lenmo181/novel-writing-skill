# -*- coding: utf-8 -*-
"""
retention_check.py — 网络小说创作技能 v7.20 留存/结构分析（热榜研究系统·写章侧消费）
用法: python retention_check.py <本章.md|txt> [--prev 上一章.md|txt]
输出: 【本章结构分析】+【留存风险分析】；全部为建议级（[i]/[!]），退出码 0=完成分析，2=输入错误。
定位: 不判文学分数、不做交付闸门（硬闸门在 check_chapter.py；跨章节奏类型归 grep_consistency.py）。
      所有指标是机械代理，语义结论（爽点/悬念/动机）仍由 AI 语义 17 项与审稿卡负责。
依据: 热榜知识库（references/热榜知识库.md）A类规律；阈值真源=常量表·九。
"""
import argparse
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 与 check_chapter.py 同口径：汉字+中文标点
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"
    "\u3000-\u303f"
    "\uff00-\uffef"
    "\u2018\u2019\u201c\u201d\u2014\u2026]"
)
SPAN_CHAL = re.compile("\u201c([^\u201c\u201d]*)\u201d|\u2018([^\u2018\u2019]*)\u2019")
ROLE_LINE = re.compile("^[\u4e00-\u9fa5A-Za-z0-9\u00b7]{1,10}\uff08[^\uff09]*\uff09\uff1a|^[\u4e00-\u9fa5A-Za-z0-9\u00b7]{1,10}\uff1a")
PANEL = re.compile("\u3010[^\u3011]*\u3011|\u300c[^\u300d]*\u300d")
ONOMATOPOEIA = re.compile("\u7830|\u8f70|\u54d4|\u5566|\u5494|\u55e1|\u6ecb|\u549a|\u5496\u5693|\u8f70\u9686")
SCENE_WORDS = re.compile("[\u5929\u98ce\u96e8\u96ea\u9633\u5149\u6708\u5149\u591c\u665a\u6e05\u6668\u508d\u665a\u6df1\u591c\u8857\u57ce\u5c71\u6751\u6cbf\u6c5f\u6d77\u96fe]")
TIME_WORDS = re.compile("\u6e05\u6668|\u508d\u665a|\u6df1\u591c|\u51cc\u6668|\u6b21\u65e5|\u7b2c\u4e00\u5929|\u7b2c\u4e8c\u5929|\u534a\u591c|\u65e5\u51fa|\u65e5\u843d|\u4e0a\u5348|\u4e0b\u5348|\u5e74|\u6708\u5e95|\u5f53\u5929|\u90a3\u5929")

W_GRAM = 3          # 与上章重复率/新词率的 n-gram 粒度
DUP_PREV_WARN = 0.40   # 与上章 3-gram 包含率警告线（知识库·十四：重复套路）
NOVEL_WARN = 0.55      # 本章新 2-gram 占比警告线（知识库·十三：信息增量底线）


TITLE_RE = re.compile(r"^\s*(?:#\s*)?第[0-9０-９零一二三四五六七八九十百千万两]{1,8}\s*[章节回]")
FORMAT_RE = re.compile(r"^\s*(?:>|```|\||---+|===+|\*{3,})")


def read_body(path):
    if not os.path.exists(path):
        return None
    raw = open(path, encoding="utf-8", errors="replace").read()
    lines = [l.rstrip() for l in raw.splitlines()]
    body_lines = []
    for l in lines:
        if not l.strip():
            if body_lines and body_lines[-1] != "":
                body_lines.append("")
            continue
        if not body_lines and TITLE_RE.match(l):
            continue
        if FORMAT_RE.match(l):
            continue
        body_lines.append(l)
    text = "\n".join(body_lines)
    paras = [re.sub(r"\s+", "", p) for p in re.split(r"\n+", text) if p.strip()]
    return [p for p in paras if p]


def ngrams(text, n):
    chars = "".join(text.split())
    return set(chars[i:i + n] for i in range(len(chars) - n + 1))


def analyze(paras):
    """→ 指标 dict；空正文返回 None（v7.25：此前 head[0] 直接 IndexError 崩溃）。"""
    if not paras:
        return None
    text = "".join(paras)
    total = len(COUNTABLE.findall(text))
    quote_chars = sum(len(m.group(1) or m.group(2) or "") for m in SPAN_CHAL.finditer(text))
    q_ratio = quote_chars / total * 100 if total else 0
    lens = [len(p) for p in paras]
    sorted_lens = sorted(lens)
    p95 = sorted_lens[int(len(sorted_lens) * 0.95)] if sorted_lens else 0
    short_share = sum(1 for l in lens if l <= 15) / len(lens) * 100 if lens else 0
    one_line = sum(1 for l in lens if l <= 20)
    quotes = len(SPAN_CHAL.findall(text))
    role_lines = sum(1 for p in paras if ROLE_LINE.match(p))
    head = paras[:3]
    tail = paras[-3:]
    # 开篇形态
    head_quote = any(p.startswith("\u201c") for p in head)
    head_ono = any(ONOMATOPOEIA.search(p) for p in head[:2])
    head_text = head[0] + (head[1] if len(head) > 1 else "")
    head_scene = (not head_quote and len(head) >= 2
                  and len(SCENE_WORDS.findall(head_text)) >= 2
                  and len(TIME_WORDS.findall(head_text)) >= 1)
    # 章末形态
    last = tail[-1] if tail else ""
    if last.endswith("\u201d"):
        end_form = "对白钩"
    elif PANEL.search(last):
        end_form = "面板/名单钩"
    elif last.endswith("？") or last.endswith("……") or (len(last) <= 15 and tail and tail[-2:] and any(t.endswith("\u201d") for t in tail)):
        end_form = "悬念短句钩"
    elif len(last) <= 20 and any(t.endswith("\u201d") for t in tail[:2]):
        end_form = "对白后短动作收"
    else:
        end_form = "陈述收（弱钩嫌疑）"
    # 章内重复（top 4-gram）
    grams4 = Counter()
    chars = "".join(text.split())
    has_hanzi = re.compile("[一-鿿]")
    for i in range(len(chars) - 3):
        g = chars[i:i + 4]
        if has_hanzi.search(g):
            grams4[g] += 1
    top_rep = grams4.most_common(1)[0] if grams4 else ("", 0)
    return {
        "total": total, "q_ratio": q_ratio, "paras": len(paras),
        "avg_len": total / len(paras) if paras else 0,
        "max_len": max(lens) if lens else 0, "p95": p95,
        "short_share": short_share, "one_line": one_line,
        "quotes": quotes, "role_lines": role_lines,
        "head_quote": head_quote, "head_ono": head_ono, "head_scene": head_scene,
        "end_form": end_form, "top_rep": top_rep,
        "grams3": ngrams(text, W_GRAM),
        "grams2": ngrams(text, 2),
    }


def main():
    ap = argparse.ArgumentParser(description="留存/结构分析 v7.20（建议级，非交付闸门）")
    ap.add_argument("file")
    ap.add_argument("--prev", help="上一章文件（启用跨章重复率与新词率）")
    args = ap.parse_args()

    paras = read_body(args.file)
    if paras is None:
        print(f"[✗] 输入错误：找不到章节文件 {args.file}")
        sys.exit(2)
    if not paras:
        print("[✗] 输入错误：文件没有可分析的正文（空文件/仅标题/仅格式行）")
        sys.exit(2)
    a = analyze(paras)

    print("=" * 46)
    print("【本章结构分析】" + os.path.basename(args.file))
    print("=" * 46)
    print(f"[i] 字数={a['total']}（可计字符） | 段落={a['paras']}段 段均={a['avg_len']:.0f}字 "
          f"最长={a['max_len']} p95={a['p95']}")
    print(f"[i] 短段(≤15字)占比={a['short_share']:.0f}% 单句段={a['one_line']}处 | 对话span={a['q_ratio']:.1f}%"
          f"（{a['quotes']}段引号）对白行={a['role_lines']}行")
    opening = []
    if a["head_quote"]:
        opening.append("引号开场")
    if a["head_ono"]:
        opening.append("拟声词开场")
    if a["head_scene"]:
        opening.append("时间/场景铺陈开场（偏慢）")
    print(f"[i] 开篇形态：{'+'.join(opening) if opening else '动作/叙述直入'} | 章末形态：{a['end_form']}")
    if a["top_rep"][1] >= 3:
        print(f"[i] 章内高频4字串：「{a['top_rep'][0]}」×{a['top_rep'][1]}（人工确认是否口头禅/复沓）")

    risks = []
    if a["q_ratio"] < 15 and a["role_lines"] < 3:
        risks.append(f"对话span {a['q_ratio']:.1f}%<15% 且无对白行体——叙述过重，读者易划走（知识库·九）")
    elif a["q_ratio"] < 15 and a["role_lines"] >= 3:
        print(f"[i] 检出对白行体（{a['role_lines']}行）——本体裁对话不以span计，勿按15%线误判（知识库·八）")
    if a["q_ratio"] > 50:
        risks.append(f"对话span {a['q_ratio']:.1f}%>50%——对话剧倾向，补叙述/动作/内心戏")
    if a["quotes"] + a["role_lines"] < 3:
        risks.append("对话交换不足3次——每章至少3次交换（SKILL 对话铁律）")
    if a["head_scene"]:
        risks.append("开篇为时间/场景铺陈——前2段必须出现钩子信号（知识库·二）")
    if a["end_form"].startswith("陈述收"):
        risks.append("章末为长陈述收尾——改为对白/画面/悬念面板/情绪句四形态之一（知识库·十一）")
    if a["avg_len"] > 60 and a["short_share"] < 10:
        risks.append("段均>60字且短段<10%——段落节奏过缓（知识库·四：短段=节奏）")

    if args.prev:
        pparas = read_body(args.prev)
        if pparas is None:
            print(f"[!] 上一章文件不可读：{args.prev}（跳过跨章分析）")
        elif not pparas:
            print(f"[!] 上一章无可分析正文：{args.prev}（跳过跨章分析）")
        else:
            b = analyze(pparas)
            contain = len(a["grams3"] & b["grams3"]) / max(len(a["grams3"]), 1)
            novel = len(a["grams2"] - b["grams2"]) / max(len(a["grams2"]), 1)
            print(f"[i] 与上章3-gram包含率={contain * 100:.0f}% | 本章新2-gram占比={novel * 100:.0f}%")
            if contain > DUP_PREV_WARN:
                risks.append(f"与上章重复率{contain * 100:.0f}%>{DUP_PREV_WARN * 100:.0f}%——疑似重复套路/水章，换冲突对象或注入新变量（打圈黑名单）")
            if novel < NOVEL_WARN:
                risks.append(f"新词占比{novel * 100:.0f}%<{NOVEL_WARN * 100:.0f}%——信息增量不足，本章读者'没多知道任何事'（知识库·十三）")

    print("=" * 46)
    print("【留存风险分析】")
    if risks:
        for r in risks:
            print(f"[!] {r}")
        print(f"小结：{len(risks)} 项风险，逐条给出修改方向后复测本脚本")
    else:
        print("[✓] 未检出机械级留存风险；爽点/悬念/动机等语义项仍需审稿卡与30项AI校验")
    sys.exit(0)


if __name__ == "__main__":
    main()
