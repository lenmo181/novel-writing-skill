# -*- coding: utf-8 -*-
"""
check_chapter.py — 网络小说创作技能 v7.19 章节机械校验脚本
用法: python check_chapter.py <章节文件.md|txt> [--min 2000] [--max 2500]
                             [--quote chal|straight|any] [--dialog-min 15] [--dialog-max 50]
只做机器可判定校验（30项中的脚本13项），语义类校验由 AI 对照 mind/ 档案执行。
退出码: 0=通过, 1=有硬伤(禁止交付), 2=输入错误(文件不存在/不可读)
输出分级: [✗] 硬伤(禁止交付) / [!] 警告(通过但必须人工过目) / [i] 信息

--quote 引号口径（同时决定"引号违规检测"与"对话占比统计"用哪套引号，二者永不错位）:
    chal     默认。中文弯引号 “ ” ‘ ’ 计入对话；半角直引号与「」判违规（长篇口径）
    straight 半角双引号 " " 计入对话；弯引号与「」判违规（短篇默认，如知乎盐选）
    any      弯引号 + 半角双引号 + 「」 都计入对话；不判任何引号违规（容错口径）
--dialog-min/--dialog-max 对话占比区间（百分数），默认 15-50（v7.19：热榜5榜5书16章全章
    span口径实测 10-49%，<15 硬卡、15-25 警告、25-50 健康指导区）；
    短剧剧本口径传 --dialog-min 60（>=55 时自动豁免上限检查）
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

# 可计数字符：汉字 + 中文标点（含弯引号、省略号、破折号）
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"
    "\u3000-\u303f"
    "\uff00-\uffef"
    "\u2018\u2019\u201c\u201d\u2014\u2026]"
)
HANZI = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")

# 对话区间正则（按 --quote 口径切换，见文件头说明）
QUOTE_MODES = ("chal", "straight", "any")
_SPAN_CHAL = re.compile("[\u201c\u2018]([^\u201c\u2018\u201d\u2019]*)[\u201d\u2019]")
_SPAN_STRAIGHT = re.compile("\"([^\"]*)\"")
_SPAN_ANY = re.compile(
    "[\u201c\u2018]([^\u201c\u2018\u201d\u2019]*)[\u201d\u2019]"
    "|\"([^\"]*)\""
    "|\u300c([^\u300c\u300d]*)\u300d"
)


def dialogue_span_re(mode):
    """返回该引号口径下的对话区间正则（必须同时用于违规检测与对话占比统计）。"""
    if mode == "straight":
        return _SPAN_STRAIGHT
    if mode == "any":
        return _SPAN_ANY
    return _SPAN_CHAL


def dialogue_chars(body, span_re):
    """累计对话区间内的可计数字符（兼容多分组正则）。"""
    total = 0
    for m in span_re.finditer(body):
        total += count_chars("".join(g for g in m.groups() if g))
    return total


def quote_violations(body, mode):
    """按口径返回引号违规描述列表（空列表=合规）。"""
    curl = sum(body.count(c) for c in "\u201c\u201d\u2018\u2019")
    straight_d = body.count("\"")
    straight_s = body.count("'")
    corner = sum(body.count(c) for c in "\u300c\u300d\u300e\u300f")
    bad = []
    if mode == "straight":
        if curl:
            bad.append(f"弯引号×{curl}")
        if corner:
            bad.append(f"直角引号×{corner}")
    elif mode == "any":
        pass  # 容错口径：不判引号违规
    else:  # chal
        if straight_d or straight_s:
            bad.append(f"半角直引号×{straight_d + straight_s}")
        if corner:
            bad.append(f"直角引号×{corner}")
    return bad

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

# v7.3 新增：AI式意象表达（出现即警告，按去AI味手册 Gate H 处理）
AI_VOGUE = [
    "空气凝固", "空气仿佛凝固", "时间仿佛静止", "时间静止", "泛起涟漪",
    "心中泛起", "如潮水般", "潮水般涌", "无形的弦", "理智的弦",
    "沉默震耳欲聋", "黑暗将他吞没", "黑暗吞没", "说不清的情绪",
    "有什么东西悄然", "这一刻，他终于明白", "这一刻，她终于明白",
    "这一刻终于明白", "千言万语", "眸色深了", "指尖发白", "指尖微微发白",
    "心脏漏跳", "呼吸一滞", "像一把刀刺入", "石子投入",
]

# 对话提示语（说道类）合计限频（v7.15：上限10→5，补齐轻声/淡淡等漏网变体）
SPEECH_TAGS = [
    "说道", "问道", "答道", "笑道", "喊道", "冷声道", "沉声道", "淡声道",
    "低声道", "高声道", "喝道", "骂道", "叹道", "喃喃道", "开口道",
    "反问道", "追问道", "接着道", "又道",
    "轻声道", "淡淡道", "应道", "回道", "嘀咕道", "嘟囔道",
    "轻声说", "低声说", "小声说", "淡淡说", "沉声说",
]
# 「他/她说：」代词+光杆引导（番茄热榜几乎绝迹的AI指纹，v7.15 新增独立检查）
# 只抓引导式（他说：“”“她说道。”“他轻声说，”），叙述转述（他说要去/他说话/他说的话）不误伤
PRONOUN_TAG_RE = re.compile(r"[他她它](?:说道?|[^的话过]{1,3}说)(?:[“：]|[，。][“])")
# v7.18 补检：行尾后缀式「”他说。」——v7.17.1 批量修复实证后缀式与前缀式同源泛滥（湘西诡闻107章209处），
# 修饰字符集与 fix_said_tags.py MOD_CH 同源（排除，的话着 防叙述误伤），≤4 字防抓长动作句
PRONOUN_TAG_SUFFIX_RE = re.compile(r"”\s*[他她它][^“”，。！？\n的话着]{0,4}说道?[，。：]?\s*$")

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
# v7.10 新增：章节名机械检查口径（真源=常量表·三B）
TITLE_PREFIX_RE = re.compile(r"^\s*第[0-9零一二三四五六七八九十百千万]{1,7}[章节回]\s*(.*)$")
TITLE_SEPARATORS_RE = re.compile(r"^[·：:、\-\s]+")
TITLE_MIN = 2   # 少于2字=无信息量，硬伤
TITLE_MAX = 12  # 番茄目录约12字截断；超长警告
# 全等命中即硬伤（空泛总结题；半空泛如「初入XX/XX前夕」归第28项 AI 语义核验）
GENERIC_TITLES = {"开端", "开始", "新的开始", "新的一天", "正文", "无题",
                  "过渡", "章节", "连载", "更新", "日常", "小插曲"}
SKIP_LINE_RE = re.compile(r"^\s*(#[^#]|>|```|\||---+|===+|\*{3,})")
MARKER_RE = re.compile(r"【[^】]*(?:段完成|累计|对话约|全章对话|广告位)[^】]*】")
# v7.17：正文里禁止夹带的元信息行（自动化写作易残留）
META_LINE_RE = re.compile(r"^\s*(?:章节更新时间|更新时间|本章字数|字数统计|总字数|发布时间)[：:]")


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


def check(path, wmin, wmax, quote_mode="chal", dialog_min=25, dialog_max=50):
    if not os.path.isfile(path):
        print(f"[✗] 输入错误：找不到章节文件 {path}")
        return 2
    try:
        text = load_text(path)
    except OSError as e:
        print(f"[✗] 输入错误：无法读取 {path}（{e}）")
        return 2
    lines, dropped = body_lines(text)
    body = "\n".join(lines)
    failures, warnings = [], []

    # ── 13 章节名规范（v7.10 新增；30项校验第13项，口径=常量表·三B）──
    title_lines = [ln.strip() for ln in text.splitlines() if TITLE_RE.match(ln)]
    title, t_len = "", 0
    if title_lines:
        if len(title_lines) > 1:
            warnings.append(f"检测到 {len(title_lines)} 个标题行——正文里混入的「第X章」行会被剔除，请核查")
        pm = TITLE_PREFIX_RE.match(title_lines[0])
        title = TITLE_SEPARATORS_RE.sub("", (pm.group(1) if pm else "").strip())
        t_len = count_chars(title)
        if not title:
            failures.append("章节名缺失：标题行只有章号没有题名（如「第3章」）——章名是目录页的一秒钩子，按《章节名规范》章名五式补起")
        elif t_len < TITLE_MIN:
            failures.append(f"章节名「{title}」仅 {t_len} 字（<{TITLE_MIN}），无信息量——按《章节名规范》重起")
        elif title in GENERIC_TITLES:
            failures.append(f"章节名「{title}」命中空泛黑名单，零钩子——按《章节名规范》章名四式（悬念反常/金手指直给/冲突预告/名台词）重起")
        elif t_len > TITLE_MAX:
            warnings.append(f"章节名「{title}」{t_len} 字 >{TITLE_MAX}（番茄目录约12字截断），压缩到钩子最亮的短句")
        else:
            print(f"[✓] 章节名「{title}」= {t_len} 字（{TITLE_MIN}-{TITLE_MAX} 区间，非黑名单）")
    else:
        warnings.append("未检测到章节标题行（第N章 XXX）——长篇落盘约定必须有；短篇单文件（正文.md）可忽略本条")

    # ── 1 字数 ──
    total = count_chars(body)
    if total < wmin:
        failures.append(f"字数 {total} < 下限 {wmin}")
    elif total > wmax:
        failures.append(f"字数 {total} > 上限 {wmax}")
    else:
        print(f"[✓] 字数 = {total}（区间 {wmin}-{wmax}）")

    # ── 2 对话占比（v7.19：<15 硬卡 / 15-25 警告 / 25-50 健康指导区 / >50 硬卡；
    #    依据热榜5榜5书16章全章 span 口径实测 10-49%；>=55 剧本口径自动跳过上限）──
    span_re = dialogue_span_re(quote_mode)
    dialog_chars = dialogue_chars(body, span_re)
    ratio = dialog_chars / total * 100 if total else 0
    if ratio < dialog_min:
        failures.append(
            f"对话占比 {ratio:.1f}% < {dialog_min}%（硬卡下限；对话约 {dialog_chars} 字，引号口径 {quote_mode}）")
    elif dialog_min < 55 and dialog_max and ratio > dialog_max:
        failures.append(
            f"对话占比 {ratio:.1f}% > 上限 {dialog_max}%（对话剧：叙述/动作/心理要占大头）")
    elif dialog_min < 55 and ratio < 25:
        warnings.append(f"对话占比 {ratio:.1f}% 偏少（{dialog_min}-25% 警告区，健康指导 25-50%）——热榜悬疑/说书体偶见，确认非注水即可")
    elif dialog_min < 55 and ratio > dialog_max - 5:
        warnings.append(f"对话占比 {ratio:.1f}% 偏高（>{dialog_max - 5}% 警告线）——补叙述、动作与内心戏")
    else:
        print(f"[✓] 对话占比 = {ratio:.1f}%（健康指导区 25-50，硬卡线 {dialog_min}-{dialog_max}，对话约 {dialog_chars} 字）")

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

    # ── 6 引号规范（口径由 --quote 决定，与第2项同源）──
    q_bad = quote_violations(body, quote_mode)
    if q_bad:
        failures.append(f"引号违规（口径 {quote_mode}）：" + "、".join(q_bad))
    else:
        print(f"[✓] 引号规范（口径 {quote_mode}）")

    # ── 7 格式残留 ──
    fmt_bad = [d for d in dropped if d.startswith("格式行")]
    if fmt_bad:
        failures.append(f"检测到格式残留（{len(fmt_bad)}行，如: {fmt_bad[0]}）")
    meta_lines = [ln for ln in lines if META_LINE_RE.match(ln)]
    if meta_lines:
        failures.append(f"元信息残留（{len(meta_lines)}行，如: {meta_lines[0].strip()[:30]}）——正文禁止夹带更新时间/字数等元数据（v7.17）")
    if quote_mode == "straight":
        n_half = body.count("\"")
        quotes_balanced = n_half % 2 == 0
        if not quotes_balanced:
            warnings.append(f"半角双引号不配对：共 {n_half} 个")
    elif quote_mode == "any":
        quotes_balanced = True
    else:
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
    silk_n = body.count("一丝")
    if silk_n > 2:
        failures.append(f"「一丝」出现 {silk_n} 次（>2 硬卡，常量表·二）——删到 ≤2，套话「眼中闪过一丝」已另在AI套话库")

    # ── v7.3：AI式意象表达（出现即警告）──
    v_hits = [(w, body.count(w)) for w in AI_VOGUE if w in body]
    if v_hits:
        warnings.append("AI式意象表达: " + "、".join(f"{w}×{n}" for w, n in v_hits) + "——抽象意象换具体动作（Gate H）")

    # ── v7.3：比喻限额（每800字≤1处明显比喻，保底2处）──
    simile_total = sum(body.count(w) for w in SIMILE_WORDS)
    simile_quota = max(2, total // 800)
    if simile_total > simile_quota:
        warnings.append(f"比喻词共 {simile_total} 处，超限额 {simile_quota}（每800字≤1处）——删掉不影响句意的比喻（Gate H）")
    else:
        print(f"[✓] 比喻词 {simile_total} 处（限额 {simile_quota}）")

    # ── 9 排版（v7.16：文字墙 160→140 硬卡 + >100 警告，热榜主流最长段≤90）──
    para_lens = [count_chars(ln) for ln in lines]
    walls = [(i + 1, n) for i, n in enumerate(para_lens) if n > 140]
    walls_warn = [(i + 1, n) for i, n in enumerate(para_lens) if 100 < n <= 140]
    if walls:
        worst = max(walls, key=lambda x: x[1])
        failures.append(f"文字墙：{len(walls)} 个段落超140字（最长第{worst[0]}段 {worst[1]} 字）——手机端必须短段，热榜主流≤90")
    else:
        if walls_warn:
            worst_w = max(walls_warn, key=lambda x: x[1])
            warnings.append(f"长段落 {len(walls_warn)} 个（>100字，最长第{worst_w[0]}段 {worst_w[1]} 字）——热榜几乎无超60字段，能拆就拆")
        print(f"[✓] 排版：最长段落 {max(para_lens) if para_lens else 0} 字，无文字墙")
    one_liners = sum(1 for ln in lines if 0 < count_chars(ln) <= 15)
    print(f"[i] 单句成段 {one_liners} 处（建议≥3处制造节奏重音）")

    # ── v7.16 新增：无引号内心戏（自由间接引语）——热榜人味核心指标 ──
    # 口径：不带引号的段落，以？/！收尾（主角视角吐槽/反问/咆哮直接成段）
    inner_voice = [ln for ln in lines if "“" not in ln and count_chars(ln) > 0 and ln.rstrip('。').endswith(("？", "！"))]
    if len(inner_voice) >= 5:
        print(f"[✓] 无引号内心戏 {len(inner_voice)} 处（≥5，主角脑子在线）")
    elif len(inner_voice) >= 3:
        warnings.append(f"无引号内心戏仅 {len(inner_voice)} 处（<5）——补主角视角吐槽/反问，热榜每章3-10处")
    else:
        warnings.append(f"无引号内心戏仅 {len(inner_voice)} 处（<3）——全书AI味重灾区：主角必须脑子在线，参考热榜『别拜了妹子！』式脑内喊话")


    # ── 警告级：情绪直贴（Show don't tell）──
    tell_hits = [m.group(0) for p in EMOTION_PATTERNS for m in p.finditer(body)]
    if tell_hits:
        warnings.append(f"情绪直贴{len(tell_hits)}处: " + "、".join(tell_hits[:6]) + "——改为动作/生理反应展示")

    # ── 警告级：对话提示语机械重复（v7.15：上限10→5）──
    tag_total = sum(body.count(t) for t in SPEECH_TAGS)
    if tag_total > 5:
        warnings.append(f"「说道/道类」提示语共 {tag_total} 次（>5）——按对话归位六式改动作归位段/裸引号")
    else:
        print(f"[✓] 对话提示语 {tag_total} 次，未超限")

    # ── 「他/她说：」光杆引导（v7.17 分级：≤2 容许 / 3-5 警告 / >5 硬卡；v7.18 并入后缀式「”他说。」）──
    pronoun_tags = [m.group(0) for m in PRONOUN_TAG_RE.finditer(body)]
    pronoun_tags += [m.group(0) for m in PRONOUN_TAG_SUFFIX_RE.finditer(body)]
    if len(pronoun_tags) > 5:
        failures.append(f"「他/她说：」类光杆引导共 {len(pronoun_tags)} 次（>5 硬卡）——代词+光杆说贴引号=热榜绝迹的AI指纹，按对话归位六式就地重写")
    elif len(pronoun_tags) > 2:
        warnings.append(f"「他/她说：」类光杆引导共 {len(pronoun_tags)} 次（3-5 警告，如 " +
                        "、".join(pronoun_tags[:4]) + "）——番茄热榜几乎绝迹，就地换动作归位段/裸引号")
    elif pronoun_tags:
        print(f"[i] 「他/她说：」类引导 {len(pronoun_tags)} 次（≤2 容许）: " + "、".join(pronoun_tags[:4]))

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
        print(f"摘要：章节名={title or '无'}({t_len}字) 字数={total} 对话占比={ratio:.1f}% 引号口径={quote_mode} —— 禁止交付，先修复再跑本脚本")
        return 1
    print(f"结论：机械校验通过 ✓（另有 {len(warnings)} 项警告需人工过目）")
    print(f"摘要：章节名={title or '无'}({t_len}字) 字数={total} 对话占比={ratio:.1f}% 引号口径={quote_mode} A级=0 套话=0")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="章节机械校验 v7.19（30项中的脚本13项，含章节名规范）",
        epilog="--quote 决定引号违规检测与对话占比统计用哪套引号，二者同源；"
               "--dialog-min/--dialog-max 默认 15/50（v7.19 热榜实证 10-49%%；>=55 剧本口径自动豁免上限）。")
    ap.add_argument("file")
    ap.add_argument("--min", type=int, default=2000, help="字数下限（默认2000，v7.19 热榜40章样本主流2000-2300）")
    ap.add_argument("--max", type=int, default=2500, help="字数上限（默认2500）")
    ap.add_argument("--quote", choices=QUOTE_MODES, default="chal",
                    help="引号口径：chal(默认,中文弯引号) / straight(半角双引号,短篇) / any(容错)")
    ap.add_argument("--dialog-min", type=int, default=15, dest="dialog_min",
                    help="对话占比硬卡下限%%（默认15；15-25警告；短剧剧本传60，>=55时自动豁免上限检查）")
    ap.add_argument("--dialog-max", type=int, default=50, dest="dialog_max",
                    help="对话占比上限%%（默认50，热榜实证；传0关闭）")
    args = ap.parse_args()
    sys.exit(check(args.file, args.min, args.max, args.quote, args.dialog_min, args.dialog_max))


if __name__ == "__main__":
    main()
