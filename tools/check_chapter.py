# -*- coding: utf-8 -*-
"""
check_chapter.py — 网络小说创作技能 v7.0 章节机械校验脚本
用法: python check_chapter.py <章节文件.md|txt> [--min 2500] [--max 3000]
只做机器可判定校验（26项中的脚本部分），语义类校验由 AI 对照 mind/ 档案执行。
退出码: 0=通过, 1=有硬伤
输出分级: [✗] 硬伤(禁止交付) / [!] 警告(通过但必须人工过目) / [i] 信息
"""
import argparse
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 可计数字符：汉字 + 中文标点（含弯引号、省略号、破折号）
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"
    "\u3000-\u303f"
    "\uff00-\uffef"
    "\u2018\u2019\u201c\u201d\u2014\u2026]"
)
HANZI = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")
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

# v6.1 新增：AI 高频套话，单词 >=3 次为硬伤
CLICHE = [
    "脸色一变", "脸色微变", "瞳孔骤缩", "瞳孔一缩", "心中一凛", "心中一沉",
    "眼中闪过", "眼底闪过", "眼中掠过", "嘴角勾起", "嘴角微扬", "嘴角上扬",
    "语气冰冷", "声音冰冷", "身子一僵", "身体一僵", "如遭雷击", "头皮发麻",
    "深吸一口气", "深吸了一口气", "攥紧了拳头", "捏紧了拳头", "握紧了拳头",
    "露出一丝", "浮现出一丝", "意味深长", "若有所思", "不置可否",
    "眼神复杂", "目光复杂", "心头一震", "心头一颤", "心中暗道", "心中一动",
]

# 对话提示语（说道类）合计限频
SPEECH_TAGS = [
    "说道", "问道", "答道", "笑道", "喊道", "冷声道", "沉声道", "淡声道",
    "低声道", "高声道", "喝道", "骂道", "叹道", "喃喃道", "开口道",
    "反问道", "追问道", "接着道", "又道",
]

EMOTION_WORDS = "愤怒悲伤高兴快乐害怕恐惧紧张失望痛苦委屈羞愧尴尬欣慰绝望无奈心疼得意后悔震惊惊讶疑惑茫然"
EMOTION_PATTERNS = [
    re.compile("[感到觉得][" + EMOTION_WORDS + "]{1,2}"),
    re.compile("(?:非常|十分|特别|无比|极其|格外)[" + EMOTION_WORDS + "]{1,2}"),
]

# 高频词检测白名单（虚词/常用组合，不计入）
BIGRAM_WHITELIST = set([
    "他们", "自己", "一个", "什么", "没有", "这个", "那个", "知道", "已经",
    "现在", "时候", "起来", "过来", "出来", "一声", "一下", "不是", "就是",
    "但是", "可是", "如果", "因为", "所以", "你们", "我们", "我的", "他的",
    "她的", "这是", "那是", "可以", "不会", "这么", "那么", "怎么", "还是",
    "也是", "都是", "说着", "看着", "对了", "说道", "話说",
])

# AI味指数（粗测）用：比喻词、情绪词
SIMILE_WORDS = ["好像", "像是", "就像", "似的", "般的", "般地"]
EMOTION_WORD_LIST = ["愤怒", "悲伤", "高兴", "快乐", "害怕", "恐惧", "紧张", "失望",
                     "痛苦", "委屈", "羞愧", "尴尬", "欣慰", "绝望", "无奈", "心疼",
                     "得意", "后悔", "震惊", "惊讶", "疑惑", "茫然"]

TITLE_RE = re.compile(r"^\s*第[0-9零一二三四五六七八九十百千万]{1,7}[章节回]")
SKIP_LINE_RE = re.compile(r"^\s*(#[^#]|>|```|\||---+|===+|\*{3,})")
MARKER_RE = re.compile(r"【[^】]*(?:段完成|累计|对话约|全章对话|广告位)[^】]*】")


def load_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def body_lines(text):
    kept, dropped = [], []
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

    # ── 1 字数 ──
    total = count_chars(body)
    if total < wmin:
        failures.append(f"字数 {total} < 下限 {wmin}")
    elif total > wmax:
        failures.append(f"字数 {total} > 上限 {wmax}")
    else:
        print(f"[✓] 字数 = {total}（区间 {wmin}-{wmax}）")

    # ── 2 对话占比 ──
    dialog_chars = sum(count_chars(m) for m in DIALOGUE_SPAN.findall(body))
    ratio = dialog_chars / total * 100 if total else 0
    if ratio < 40:
        failures.append(f"对话占比 {ratio:.1f}% < 40%（对话约 {dialog_chars} 字）")
    else:
        print(f"[✓] 对话占比 = {ratio:.1f}%（对话约 {dialog_chars} 字）")

    # ── 3 A级禁言词 ──
    a_hits = [(w, body.count(w)) for w in A_LEVEL if w in body]
    if a_hits:
        failures.append("A级禁言词出现: " + "、".join(f"{w}×{n}" for w, n in a_hits))
    else:
        print("[✓] A级禁言词 = 0")

    # ── 4 B级限制词 ──
    b_hits = [(w, body.count(w)) for w in B_LEVEL if body.count(w) > 3]
    if b_hits:
        warnings.append("B级限制词超频(>3): " + "、".join(f"{w}×{n}" for w, n in b_hits))
    else:
        print("[✓] B级限制词均在限额内")

    # ── 5 破折号 ──
    dash = body.count("——")
    if dash > 2:
        failures.append(f"破折号——出现 {dash} 次 > 上限 2")
    else:
        print(f"[✓] 破折号—— = {dash} 次")

    # ── 6 引号规范 ──
    straight = sum(body.count(c) for c in "\"'")
    corner = sum(body.count(c) for c in "「」『』")
    if straight or corner:
        failures.append(f"引号违规：半角直引号×{straight}，直角引号×{corner}（必须用弯引号）")
    else:
        print("[✓] 引号规范（中文弯引号）")

    # ── 7 格式残留 ──
    fmt_bad = [d for d in dropped if d.startswith("格式行")]
    if fmt_bad:
        failures.append(f"检测到格式残留（{len(fmt_bad)}行，如: {fmt_bad[0]}）")
    quotes_balanced = body.count("\u201c") == body.count("\u201d")
    if not quotes_balanced:
        warnings.append(f"弯引号不配对：左 {body.count(chr(0x201c))} / 右 {body.count(chr(0x201d))}")
    if not fmt_bad and quotes_balanced:
        print("[✓] 无格式残留")

    # ── 8 AI套话（v6.1）──
    c_hits = [(w, body.count(w)) for w in CLICHE if body.count(w) >= 3]
    if c_hits:
        failures.append("AI套话超频(≥3): " + "、".join(f"{w}×{n}" for w, n in c_hits))
    else:
        print("[✓] AI套话均在限额内")
    if body.count("一丝") > 2:
        warnings.append(f"「一丝」出现 {body.count('丝')} 次级联（'一丝'×{body.count('一丝')}，>2 建议删减）")

    # ── 9 排版（v6.1）──
    para_lens = [count_chars(ln) for ln in lines]
    walls = [(i + 1, n) for i, n in enumerate(para_lens) if n > 160]
    if walls:
        worst = max(walls, key=lambda x: x[1])
        failures.append(f"文字墙：{len(walls)} 个段落超160字（最长第{worst[0]}段 {worst[1]} 字）——手机端必须短段")
    else:
        print(f"[✓] 排版：最长段落 {max(para_lens) if para_lens else 0} 字，无文字墙")
    one_liners = sum(1 for ln in lines if 0 < count_chars(ln) <= 15)
    print(f"[i] 单句成段 {one_liners} 处（建议≥3处制造节奏重音）")

    # ── 警告级：情绪直贴（Show don't tell）──
    tell_hits = [m.group(0) for p in EMOTION_PATTERNS for m in p.finditer(body)]
    if tell_hits:
        warnings.append(f"情绪直贴{len(tell_hits)}处: " + "、".join(tell_hits[:6]) + "——改为动作/生理反应展示")

    # ── 警告级：对话提示语机械重复 ──
    tag_total = sum(body.count(t) for t in SPEECH_TAGS)
    if tag_total > 10:
        warnings.append(f"「说道/问道类」提示语共 {tag_total} 次（>10）——用动作beat替代或省略提示语")
    else:
        print(f"[✓] 对话提示语 {tag_total} 次，未机械重复")

    # ── 警告级：高频二字词近距离复用 ──
    hanzi_only = "".join(ch for ch in body if HANZI.match(ch))
    grams = Counter(hanzi_only[i:i + 2] for i in range(len(hanzi_only) - 1))
    hot = [(w, n) for w, n in grams.most_common(8)
           if n >= 8 and w not in BIGRAM_WHITELIST and not (w[0] == w[1])]
    if hot:
        warnings.append("高频词疑似复用: " + "、".join(f"「{w}」×{n}" for w, n in hot) + "——查是否同词近距离重复")

    # ── 信息级：AI味指数（粗测，0-10，越高越要人工过目）──
    import statistics
    sents = [s for s in re.split("[。！？…]+", body) if count_chars(s) > 0]
    sent_lens = [count_chars(s) for s in sents]
    sent_sd = statistics.pstdev(sent_lens) if len(sent_lens) > 3 else 20
    para_sd = statistics.pstdev(para_lens) if len(para_lens) > 3 else 60
    simile = sum(body.count(w) for w in SIMILE_WORDS)
    emo = sum(body.count(w) for w in EMOTION_WORD_LIST)
    simile_d = simile / total * 1000 if total else 0
    emo_d = emo / total * 1000 if total else 0
    avg_sents_per_para = len(sents) / len(lines) if lines else 0
    score = 0
    reasons = []
    if sent_sd < 8:
        score += 2; reasons.append(f"句长波动低(sd={sent_sd:.0f})")
    if para_sd < 30:
        score += 2; reasons.append(f"段长波动低(sd={para_sd:.0f})")
    if simile_d >= 6:
        score += 2; reasons.append(f"比喻词密度{simile_d:.1f}/千字")
    if emo_d >= 6:
        score += 2; reasons.append(f"情绪词密度{emo_d:.1f}/千字")
    if avg_sents_per_para > 5:
        score += 2; reasons.append(f"平均每段{avg_sents_per_para:.1f}句")
    print(f"[i] AI味指数(粗测) = {score}/10" + ("：" + "；".join(reasons) if reasons else "，机器指标均正常"))

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
    print(f"结论：机械校验通过 ✓（另有 {len(warnings)} 项警告需人工过目）")
    print(f"摘要：字数={total} 对话占比={ratio:.1f}% A级=0 套话=0")
    return 0


def main():
    ap = argparse.ArgumentParser(description="章节机械校验 v6.1")
    ap.add_argument("file")
    ap.add_argument("--min", type=int, default=2500)
    ap.add_argument("--max", type=int, default=3000)
    args = ap.parse_args()
    sys.exit(check(args.file, args.min, args.max))


if __name__ == "__main__":
    main()
