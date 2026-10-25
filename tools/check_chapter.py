# -*- coding: utf-8 -*-
"""
check_chapter.py — 网络小说创作技能 v7.35 章节机械校验脚本
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
--ai-lite 只跑零依赖 AI 味粗测，不执行完整章节硬卡；适合没有墨尺服务时先做初筛。
    v7.40 起粗测升级为百分制人类分 + 句法/节奏/人味三维短板（口径对齐朱雀/墨尺的
    「≥90 达标 / 80-89 警告 / <80 需改写」，本地启发式定位用，不替代模型结论）。
--chapter-index N 章节序号（1 起）。N≤3 时启用**前3章开篇闸门**（黄金开篇铁律，
    推荐位生死线）：禁开头8条逐条机械检测 + 前300字「人物+异常」+ 前3段钩子信号≥1，
    命中即硬伤禁止交付；未传参时自动从标题行「第N章」推断。N>3 或无标题且未传参则跳过。
"""
import argparse
import os
import re
import sys
from collections import Counter

import config
from config import (
    AI_TASTE_CONTRAST_MAX,
    AI_TASTE_IMAGERY_MAX_PER_K,
    AI_TASTE_IMAGERY_MIN_LEN,
    DEFAULT_AI_SCORE_HARD_MAX,
    DEFAULT_CHAPTER_MAX,
    DEFAULT_CHAPTER_MIN,
    DEFAULT_DIALOG_MAX,
    DEFAULT_DIALOG_MIN,
    OPENING_GATE_CHAPTERS,
    OPENING_PARAS,
    OPENING_WINDOW_CHARS,
    SKILL_VERSION,
    TITLE_MAX,
    TITLE_MIN,
    WALL_HARD,
    WALL_WARN,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 可计数字符：汉字 + 中文标点（含弯引号、省略号、破折号）
# v7.47：排除 U+3000 全角空格本身——此前首行缩进「　　他说」每段 +2 可计字符，
# 100 章 = +200 字注水，可能把 1830 净字顶过 2000 下限（虚假通过）
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"
    "\u3001-\u303f"
    "\uff00-\uffef"
    "\u2018\u2019\u201c\u201d\u2014\u2026]"
)
HANZI = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")

# 对话区间正则（按 --quote 口径切换，见文件头说明）
QUOTE_MODES = ("chal", "straight", "any")
DIALOG_MIN_DEFAULT = DEFAULT_DIALOG_MIN
DIALOG_MAX_DEFAULT = DEFAULT_DIALOG_MAX
AI_SCORE_HARD_MAX = DEFAULT_AI_SCORE_HARD_MAX
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
        # v7.47：半角单引号 ' 不计违规——中英混排文本 don't/it's 合法存在，
        # 中文弯引号流里 ASCII 撇号无引号用途，计入会误伤（此前假阳性硬伤）
        if straight_d:
            bad.append(f"半角直引号×{straight_d}")
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
# v7.25：加 re.MULTILINE——此前 $ 只匹配全文末尾，正文中段的后缀式全部漏计
PRONOUN_TAG_SUFFIX_RE = re.compile(r"”\s*[他她它][^“”，。！？\n的话着]{0,4}说道?[，。：]?\s*$", re.MULTILINE)

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
    "也是", "都是", "说着", "看着", "对了", "说道", "话说",
])

# AI味指数（粗测）用：比喻词、情绪词
SIMILE_WORDS = ["好像", "像是", "就像", "似的", "般的", "般地"]

# ── v7.49 量化 AI 味硬指标（对标 chinese-novelist-skill 量化口径）──
# 「不是A是B」句式：AI 生成文本最稳定的结构指纹之一。
# 覆盖「不是…而是…」「不是…是…」「并非…而是…」三类，命中即计一处。
CONTRAST_RE = re.compile(
    r"(?:不是|并非)[^，。！？；：\n]{1,12}?(?:而是|是)|"
    r"(?:不是|并非)[^，。！？；：\n]{1,12}?[，、][^，。！？；：\n]{0,8}?是"
)
# 单一意象：比喻词/形容骨架引出的意象词（如「月光」「刀锋」「雪」）。
# 只统计长度 ≥ AI_TASTE_IMAGERY_MIN_LEN 的意象，单字不计入。
# 识别两类：(1) 比喻词领起（像月光一般）；(2) 意象词直接作主语（月光洒在刀上）。
# 第二类是网文里更常见的写法——若只认比喻词领起，会漏掉绝大多数重复意象。
IMAGERY_LEAD_RE = re.compile(
    r"(?:像|如同|仿佛|犹如|好似|宛如|好像|像是|就像|似的|一般|般地|如)"
    r"(?:是|着|的)?\s*([一-鿿]{%d,4})" % AI_TASTE_IMAGERY_MIN_LEN
)
# 意象词直接作主语：句首 2-4 字意象词 + 动作/形容
IMAGERY_SUBJ_RE = re.compile(
    r"(?:^|[。！？；：\n“”])\s*([一-鿿]{%d,4}?)(?=洒|落|沉|铺|照|映|闪|晃|流|飘|染|爬|淌|蔓|爬升|浮|裂|燃|滚|压|罩|笼|悬)"
    % AI_TASTE_IMAGERY_MIN_LEN
)


def count_contrast_patterns(body):
    """统计「不是A是B」句式处数（AI 结构指纹）。"""
    return len(CONTRAST_RE.findall(body))


def count_repeated_imagery(body):
    """统计同一意象在同一章内的重复次数。

    返回 [(意象, 次数), ...]，只保留出现 ≥2 次的意象，按次数降序。
    两类写法都计入：比喻词领起（像月光一般）与意象词直接作主语（月光洒在刀上）。
    """
    counts = Counter()
    for m in IMAGERY_LEAD_RE.finditer(body):
        counts[m.group(1)] += 1
    for m in IMAGERY_SUBJ_RE.finditer(body):
        counts[m.group(1)] += 1
    return [(word, n) for word, n in counts.most_common() if n >= 2]
EMOTION_WORD_LIST = ["愤怒", "悲伤", "高兴", "快乐", "害怕", "恐惧", "紧张", "失望",
                     "痛苦", "委屈", "羞愧", "尴尬", "欣慰", "绝望", "无奈", "心疼",
                     "得意", "后悔", "震惊", "惊讶", "疑惑", "茫然"]

# v7.47：统一章节标题口径（对齐 retention_check.py:41）——支持全角数字、「两」、
# 第与数字间空格（此前 `第３章`/`第 3 章` 不识别 → 第13项与开篇闸门静默跳过）
TITLE_RE = re.compile(r"^\s*第[0-9０-９零一二三四五六七八九十百千万两]{1,7}\s*[章节回]")
# v7.10 新增：章节名机械检查口径（真源=常量表·三B）
TITLE_PREFIX_RE = re.compile(r"^\s*第[0-9０-９零一二三四五六七八九十百千万两]{1,7}\s*[章节回]\s*(.*)$")
TITLE_SEPARATORS_RE = re.compile(r"^[·：:、\-\s]+")
# 全等命中即硬伤（空泛总结题；半空泛如「初入XX/XX前夕」归第28项 AI 语义核验）
GENERIC_TITLES = {"开端", "开始", "新的开始", "新的一天", "正文", "无题",
                  "过渡", "章节", "连载", "更新", "日常", "小插曲"}
# v7.47：`#{1,6}\s` 替代 `#[^#]`——此前 `## 小节标题`/`### 小节` 不匹配任何剔除规则，
# 静默计入正文（参与字数/词频统计，可能把 1998 字顶过 2000 下限造成虚假通过）
SKIP_LINE_RE = re.compile(r"^\s*(?:#{1,6}\s|>|```|\||-{3,}|={3,}|\*{3,})")
MARKER_RE = re.compile(r"【[^】]*(?:段完成|累计|对话约|全章对话|广告位)[^】]*】")
# v7.17：正文里禁止夹带的元信息行（自动化写作易残留）
META_LINE_RE = re.compile(r"^\s*(?:章节更新时间|更新时间|本章字数|字数统计|总字数|发布时间)[：:]")

# ═══════════════ 前3章开篇闸门（v7.40，黄金开篇铁律：推荐位生死线）═══════════════
# 禁开头8条的可机械形态 + 前300字「人物+异常」+ 前3段钩子信号。全部只看开篇窗口，
# 不追溯正文后段；题材例外（说书体等）经书格裁决，本闸门不设 --wall 式参数放宽。

# ① 天气/景色/时间交代（首句命中且首句无任何人物信号才算——有人物在做事不算铺陈开场）
WEATHER_TIME_OPEN_RE = re.compile(
    "^(今天|今夜|今晨|清晨|早晨|凌晨|黎明|天刚|天色|傍晚|黄昏|深夜|午夜|正午|晌午|"
    "夜幕|夜色|月色|月光|夜空|天空|天边|太阳|烈日|骄阳|朝阳|晨光|暮色|夕阳|残阳|晚霞|朝霞|"
    "乌云|白云|云层|细雨|小雨|中雨|大雨|暴雨|雷雨|雨水|雨丝|雨点|雪花|大雪|暴雪|狂风|风雪|"
    "微风|春风|秋风|寒风|冷风|薄雾|浓雾|晨雾|雾气|空气|盛夏|酷暑|炎夏|寒冬|深秋|初秋|初春|"
    "盛春|群山|大山|深山|山脚|森林|密林|树林|竹林|河流|大江|江水|河水|湖水|湖面|大海|海面|"
    "海浪|草原|戈壁|沙漠|小镇|村庄|小村|古城|老街|青石板|城池|宫殿|城墙|庭院|深宫)"
)
# 人物信号（用于①的排除条件与前300字「人物」检测）：人称代词，或「二至四字名词+常见动作动词」
NAME_ACTION_RE = re.compile(
    "[\u4e00-\u9fff]{2,4}(?:推|拉|抓|拿|提|扛|背|抱|喊|叫|嚷|吼|骂|冲|奔|跑|逃|追|走|来|去|回|进|出|上|下|"
    "站|坐|蹲|跪|爬|跳|扑|挡|拔|翻|扔|捡|拾|敲|拍|掐|咬|踢|踹|蹬|躲|藏|缩|拦|拽|扯|抬|举|放|松|握|攥|"
    "盯|望|看|瞧|瞥|听|闻|嗅|说|道|问|答|喊|叫|笑|哭|叹|哼|骂|想|记|数|算|皱|眯|咽|喘|颤|抖)"
)
PRONOUN_RE = re.compile(r"[他她我它你]")
# ②③ 做梦梦醒 / "XX睁开眼"式醒来（只看开篇窗口）
DREAM_OPEN_RE = re.compile(r"梦[中境]|梦里|做梦|一场梦|是梦|噩?梦(?:惊|吵)?醒|从梦中|惊醒")
# v7.47：删「睡意」——「压下睡意/毫无睡意」是清醒场景，不是醒来信号（此前假阳性硬伤）
WAKE_OPEN_RE = re.compile(r"睁开[了双一一]?.{0,2}眼|睁眼|醒了过来|醒了|睡眼")
# ④ 照镜子自视外貌
MIRROR_OPEN_RE = re.compile(
    r"(?:铜?镜[子里的面]{1,2}|镜中|镜里|倒影)(?:[^。！？\n]{0,14})"
    r"(自己|这张脸|脸|眉|眼|眸|容颜|容貌|模样|长相|身材|皮肤|肤)"
)
# ⑤ 大段回忆身世倒叙（前3段叙述部分命中≥2个标记）
# v7.47：改正则非重叠匹配（长词优先）——此前 sum(count(w)) 让「回忆」⊂「回忆起」、
# 「记忆」⊂「记忆里」同一短语重复计数，单个回忆短语即凑够 2 个标记触发硬伤（假阳性）
RECALL_RE = re.compile(
    "多年前|十年前|数年前|几十年前|想当年|自幼|从小|小时候|"
    "回忆起|记忆里|记忆中|曾记得|往事|往昔|身世|回忆|那年|曾经"
)
# ⑥ 世界观解说（前3段叙述部分命中即中——只抓说书腔也救不了的旁白解说）
EXPO_MARKERS = ["在这个世界", "这方世界", "众所周知", "所谓的", "修仙界", "修行界", "大陆上",
                "自古以来", "世界规则", "灵气复苏", "天地间有", "世间万物"]
# ⑧ 日常流水账（前3段命中≥3个标记）
ROUTINE_MARKERS = ["起床", "洗漱", "早饭", "早餐", "午饭", "晚饭", "做饭", "买菜", "上学", "放学",
                   "下班", "上班", "打卡", "地铁", "公交", "打扫", "洗衣", "收拾屋子", "熬了夜", "睡觉"]
# 前300字「异常」信号与前3段「钩子信号」共用词族（黄金开篇：人物+异常；开篇三句入戏）
HOOK_SUSPENSE_WORDS = [
    "竟然", "居然", "忽然", "突然", "陡然", "猛然", "蓦然", "不对劲", "不对", "不妙", "诡异",
    "奇怪", "怪异", "莫名", "离奇", "异常", "反常", "邪门", "危机", "危险", "杀", "死", "尸",
    "血", "惊", "炸", "轰", "砰", "嘶", "吼", "惨叫", "尖叫", "怒吼", "咆哮", "倒计时", "面板",
    "系统", "金手指", "秘密", "禁忌", "诅咒", "鬼", "妖", "魔", "邪", "变故", "异动", "消失",
    "不见了", "出事", "救命", "滚开", "站住", "别动", "抓住", "凶手", "黑影", "敌", "贼",
    "匪", "劫", "叛", "背叛", "出卖", "下毒", "暗算", "埋伏", "盯上", "跟踪", "疯",
]
HOOK_TENSE_VERBS = ["盯", "攥", "拽", "躲", "藏", "屏息", "屏住", "压低声音", "压着嗓子",
                    "蹑手蹑脚", "小心翼翼", "警惕", "戒备", "防备", "潜伏", "潜入", "偷"]
HOOK_PANEL_MARKS = ["【", "倒计时", "剩余时间", "限时"]


def _clamp100(v):
    return max(0.0, min(100.0, v))


def count_hook_signals(segment):
    """返回 segment 内钩子信号总数（悬念词/紧张动作/面板/强标点各计其数）。"""
    n = sum(segment.count(w) for w in HOOK_SUSPENSE_WORDS)
    n += sum(segment.count(w) for w in HOOK_TENSE_VERBS)
    n += sum(segment.count(w) for w in HOOK_PANEL_MARKS)
    n += segment.count("！") + segment.count("？")
    return n


def person_signal(segment):
    """人物信号：人称代词≥2，或存在「名词+动作」结构，或代词≥1 且有姓名式三字词。"""
    pron = len(PRONOUN_RE.findall(segment))
    if pron >= 2 or NAME_ACTION_RE.search(segment):
        return True
    return pron >= 1 and re.search(r"[\u4e00-\u9fff]{2,3}(?:说道|喊道|想着|知道|明白)", segment) is not None


def strip_dialogue(body, span_re):
    """把对话区间替换为全角空格，返回纯叙述文本（解说/回忆检测用，防对话内误伤）。"""
    def _blank(m):
        return "\u3000" * len(m.group(0))
    return span_re.sub(_blank, body)


def first_countable(body, limit):
    """取正文前 limit 个可计数字符组成的检测窗。"""
    return "".join(COUNTABLE.findall(body)[:limit])


# 章节序号中文数字解析（标题行「第N章」自动推断 --chapter-index 用，覆盖到千）
_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(s):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s or any(ch not in _CN_DIGIT and ch not in "十百千" for ch in s):
        return None
    total, num = 0, 0
    for ch in s:
        d = _CN_DIGIT.get(ch)
        if d is not None:
            num = num * 10 + d if num else d if d else num
        elif ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch == "百":
            total += (num or 1) * 100
            num = 0
        elif ch == "千":
            total += (num or 1) * 1000
            num = 0
    return total + num


def infer_chapter_index(text):
    """从标题行「第N章」推断章节序号；推不出返回 None。"""
    m = TITLE_RE.match(text.strip())
    if not m:
        for ln in text.splitlines():
            m = TITLE_RE.match(ln.strip())
            if m:
                break
    if not m:
        return None
    return cn_to_int(m.group(0).strip()[1:-1])


def opening_gate(body, lines, span_re, chapter_index, failures, warnings):
    """前3章开篇专项（黄金开篇铁律）。命中禁开头/缺人物异常/无钩子 = 硬伤。"""
    paras = lines[:OPENING_PARAS]
    head = "".join(paras)
    narration = strip_dialogue(head, span_re)
    window = first_countable(body, OPENING_WINDOW_CHARS)
    hits = []

    def para_dialogue_ratio(p):
        t = count_chars(p)
        return (dialogue_chars(p, span_re) / t) if t else 0.0

    # ① 天气/景色/时间交代：首句（前两个句读单元）命中且整句无人物信号
    first_sent = re.split("[。！？…]", head, maxsplit=1)[0]
    wm = WEATHER_TIME_OPEN_RE.match(head.lstrip("\u3000“\"「"))
    if wm and not person_signal(first_sent):
        hits.append(f"禁开头①「{wm.group(1)}」天气/景色/时间开场——第一句禁铺陈交代，改人物+动作直入")

    # ② 做梦梦醒
    if DREAM_OPEN_RE.search(window):
        hits.append("禁开头② 做梦/梦醒开场——梦境开头读者直接划走，改真实事件")
    # ③ "XX睁开眼"式醒来（窗口更窄：前120可计数字符）
    wake_win = first_countable(body, 120)
    if WAKE_OPEN_RE.search(wake_win):
        hits.append("禁开头③「睁开眼/醒来」式开场——穿越重生老套起手，直接从事件中间写起")
    # ④ 照镜子自视外貌
    mm = MIRROR_OPEN_RE.search(window)
    if mm:
        hits.append(f"禁开头④ 照镜子自视外貌（…{mm.group(0)[:12]}…）——外貌写进动作与他人反应")
    # ⑤ 大段回忆身世倒叙：前3段叙述部分≥2个标记（v7.47 非重叠计数）
    recall_n = len(RECALL_RE.findall(narration))
    if recall_n >= 2:
        hits.append(f"禁开头⑤ 回忆身世倒叙嫌疑（前3段命中{recall_n}个回忆标记）——回忆切碎塞进当下事件")
    # ⑥ 世界观解说
    expo_hits = [w for w in EXPO_MARKERS if w in narration]
    if expo_hits:
        hits.append(f"禁开头⑥ 世界观解说腔（{expo_hits[0]}…）——设定拆进冲突对话与事件")
    # ⑦ 无事件纯对话：前3段全部对话主导
    if paras and len(paras) >= OPENING_PARAS and all(para_dialogue_ratio(p) >= 0.6 for p in paras):
        hits.append("禁开头⑦ 无事件纯对话开场——对话前先给一个动作/异常锚点")
    # ⑧ 日常流水账：前3段≥3个日常标记
    routine_n = sum(head.count(w) for w in ROUTINE_MARKERS)
    if routine_n >= 3:
        hits.append(f"禁开头⑧ 日常流水账嫌疑（命中{routine_n}个日常标记）——删日常，直入异常事件")
    # 时间戳+场景铺陈不得占前2段以上（开篇三句入戏条款）：无对话且含铺陈词的段计数
    filler_paras = 0
    for p in paras:
        if para_dialogue_ratio(p) < 0.15 and WEATHER_TIME_OPEN_RE.search(p.lstrip("\u3000")):
            filler_paras += 1
    if paras and filler_paras > 2:
        hits.append("开篇三句入戏：时间/场景铺陈占满前3段——留1段，其余改人物+事件")

    # 前300字手术标准：人物 + 异常
    person_ok = person_signal(window)
    anomaly_n = count_hook_signals(window)
    if not person_ok:
        hits.append("前300字无人物信号——第一屏必须出现人物（人物+异常手术标准）")
    if anomaly_n == 0:
        hits.append("前300字无异常/冲突信号——第一屏必须让读者产生问号（悬念词/危机对话/反常动作）")
    # 开篇三句入戏：前3段钩子信号≥1
    hook_n = count_hook_signals(head)
    if hook_n == 0:
        hits.append("前3段无钩子信号——开篇三句入戏：冲突动作/危机对话/异动悬念/倒计时面板至少其一")

    if hits:
        for h in hits:
            failures.append(f"开篇闸门（第{chapter_index}章·生死线）：{h}")
        return
    print(f"[✓] 开篇闸门（第{chapter_index}章·生死线）：禁开头8条 0 命中；前300字人物+异常齐备；"
          f"前3段钩子信号 {hook_n} 处")


# ═══════════════ 对话三症状（第20项，v7.40 警告级机械线索 → AI 语义复核）═══════════════
LECTURE_MARKERS = ["所谓", "是指", "分为", "共有", "位于", "等级", "境界", "大陆", "王朝", "宗门",
                   "门派", "体系", "由来", "上古", "洪荒", "灵气", "修为", "律法", "规矩是"]
JEST_MARKERS = ["哈哈", "笑死", "绝了", "离谱", "牛啊", "666", "梗", "绷不住", "乐了"]


def dialogue_symptom_checks(body, lines, span_re, warnings):
    """对话三症状的机械线索（警告级，给第20项 AI 语义复核供证据，不抢判定）。"""
    # 症状1 机械问答式对称：连续≥4个对话主导段且长度高度接近
    ratios = []
    for p in lines:
        t = count_chars(p)
        ratios.append((dialogue_chars(p, span_re) / t if t else 0.0, t))
    run = []
    runs = []
    for r, t in ratios:
        if r >= 0.5 and t > 0:
            run.append(t)
        else:
            if len(run) >= 4:
                runs.append(run)
            run = []
    if len(run) >= 4:
        runs.append(run)
    for seg in runs:
        if min(seg) / max(seg) >= 0.7:
            warnings.append(f"对话三症状·机械问答对称嫌疑：连续{len(seg)}段对话长度高度接近"
                            f"（{min(seg)}-{max(seg)}字）——一问一答字数对等是AI指纹，制造长短差/打断/答非所问")
            break
    # 症状2 科普嘴讲设定：长对话段设定名词密度高
    lectures = []
    for m in span_re.finditer(body):
        span = "".join(g for g in m.groups() if g) or m.group(0)
        if count_chars(span) < 60:
            continue
        n = sum(span.count(w) for w in LECTURE_MARKERS)
        if n >= 2 or (count_chars(span) >= 90 and n >= 1):
            lectures.append(span.strip()[:24])
    if lectures:
        warnings.append(f"对话三症状·科普嘴嫌疑：{len(lectures)}段长对话设定名词密集"
                        f"（如“{lectures[0]}…”）——设定拆进冲突与代价，不进讲解")
    # 症状3 不分场合插科打诨
    jest_n = 0
    for m in span_re.finditer(body):
        span = "".join(g for g in m.groups() if g) or m.group(0)
        if any(w in span for w in JEST_MARKERS):
            jest_n += 1
    if jest_n >= 2:
        warnings.append(f"对话三症状·插科打诨嫌疑：{jest_n}段对话含玩梗/大笑标记——核对场合是否成立（悲壮/危机戏禁用）")


def load_text(path):
    # utf-8-sig：BOM 不剥离会使首行 ^锚定失效（TITLE_RE 不命中 → 标题计入正文、
    # 章节名校验整体跳过）；errors=replace 防单字节坏点中断全章分析（v7.30）
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def body_lines(text):
    """切出正文行与被剔除行。
    标题剔除口径（v7.25 收紧）：裸「第X章」只剔首个标题行（标题在文件头）；正文中段的
    「第三回交手，…」这类叙述行按正文保留参与全部校验（此前整段被当标题剔除，漏检硬伤）。
    「#」开头的标题行任何位置都剔（markdown 标题=格式行，无歧义）。"""
    kept, dropped = [], []
    seen_title = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        # 「# 第X章」标题：剥掉 # 前缀后再按标题识别（v7.30——此前 match 目标是含 #
        # 的原行而 TITLE_RE 要求「第」开头，条件恒假成死分支，# 标题被当格式行剔除
        # 且「未检测到章节标题行」误报）
        if TITLE_RE.match(stripped.lstrip("#").lstrip()) and (stripped.startswith("#") or not seen_title):
            seen_title = True
            dropped.append("章节标题: " + line.strip()[:30])
            continue
        if SKIP_LINE_RE.match(line):
            dropped.append("格式行: " + line.strip()[:30])
            continue
        kept.append(MARKER_RE.sub("", line))
    return kept, dropped


def count_chars(s):
    return len(COUNTABLE.findall(s))


def ai_lite_score(body, lines):
    """返回零依赖启发式 AI 味粗测分数（0-10，越高越需要人工过目）。

    维度映射（v7.33 对齐《去AI味》AI味八维）：
      节奏AI味：句长/段长波动低；语言AI味：比喻词密度；情绪AI味：情绪词密度；
      结构AI味：章内 5-gram 自重复率高；解释AI味：平均每段句数过多。
    v7.40：metrics 附带百分制三维短板（句法/节奏/人味，0-100 越低越要改）与
    人类分粗测（=(10-score)×10，口径对齐朱雀/墨尺百分制，供定位与复测基线）。
    """
    import statistics

    total = count_chars(body)
    sents = [s for s in re.split("[。！？…]+", body) if count_chars(s) > 0]
    sent_lens = [count_chars(s) for s in sents]
    para_lens = [count_chars(ln) for ln in lines]
    # v7.47：仅空列表取默认兜底（防 StatisticsError），1-3 句实算——
    # 此前 ≤3 句恒取虚高默认 20/60，短篇章节 AI 指标无区分度
    sent_sd = statistics.pstdev(sent_lens) if sent_lens else 20.0
    para_sd = statistics.pstdev(para_lens) if para_lens else 60.0
    simile = sum(body.count(w) for w in SIMILE_WORDS)
    emo = sum(body.count(w) for w in EMOTION_WORD_LIST)
    simile_d = simile / total * 1000 if total else 0
    emo_d = emo / total * 1000 if total else 0
    avg_sents_per_para = len(sents) / len(lines) if lines else 0
    clean = re.sub(r"\s+", "", body)
    grams5 = [clean[i:i + 5] for i in range(len(clean) - 4)]
    dup5 = len(grams5) - len(set(grams5))
    dup5_pct = dup5 * 100 / len(grams5) if grams5 else 0
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
    if dup5_pct >= 2:
        score += 1; reasons.append(f"章内5-gram自重复率{dup5_pct:.1f}%")
    score = min(score, 10)
    # ── v7.40 百分制三维短板（连续分供定向改写；合成人类分仍由 0-10 口径换算，二者不混用）──
    one_liners = sum(1 for ln in lines if 0 < count_chars(ln) <= 15)
    inner_voice = sum(1 for ln in lines
                      if "“" not in ln and count_chars(ln) > 0 and ln.rstrip('。').endswith(("？", "！")))
    dim_syntax = _clamp100((sent_sd - 5) / 20 * 100)
    dim_rhythm = _clamp100(0.55 * ((para_sd - 20) / 80 * 100) + 0.45 * (one_liners / 6 * 100))
    dim_flavor = _clamp100(0.25 * ((6 - simile_d) / 4 * 100) + 0.25 * ((6 - emo_d) / 4 * 100)
                           + 0.25 * (inner_voice / 5 * 100) + 0.25 * ((2 - dup5_pct) / 1.5 * 100))
    dims = {"句法": round(dim_syntax), "节奏": round(dim_rhythm), "人味": round(dim_flavor)}
    return score, reasons, {
        "chars": total,
        "sent_sd": sent_sd,
        "para_sd": para_sd,
        "simile_per_k": simile_d,
        "emotion_per_k": emo_d,
        "avg_sentences_per_paragraph": avg_sents_per_para,
        "dup5_pct": round(dup5_pct, 2),
        "one_liners": one_liners,
        "inner_voice": inner_voice,
        "dims": dims,
        "human_score": (10 - score) * 10,
    }


DIM_GATE_HINTS = {
    "句法": "Gate B 拆书面句式、制造长短差",
    "节奏": "Gate D 长短句对比/单句成段重音",
    "人味": "Gate E 对话口头禅/打断/改口 + Gate H 情绪换动作",
}


def weak_dim_hint(dims, floor=40):
    """短板维度提示（<floor 的维度按分值升序列出，附 Gate 定向改写建议）。"""
    weak = [(k, v) for k, v in sorted(dims.items(), key=lambda kv: kv[1]) if v < floor]
    if not weak:
        return ""
    parts = [f"{k}({v})→{DIM_GATE_HINTS[k]}" for k, v in weak]
    return "短板维度：" + "；".join(parts)


def ai_lite_check(path):
    """免依赖 AI 味初筛：只给启发式指标，不影响章节交付结论。"""
    if not os.path.isfile(path):
        print(f"[✗] 输入错误：找不到章节文件 {path}")
        return 2
    try:
        text = load_text(path)
    except OSError as e:
        print(f"[✗] 输入错误：无法读取 {path}（{e}）")
        return 2
    lines, _ = body_lines(text)
    score, reasons, metrics = ai_lite_score("\n".join(lines), lines)
    dims = metrics["dims"]
    print(f"[i] AI味粗测 = {score}/10（越高越需要人工过目）")
    print(f"[i] 人类分(粗测) = {metrics['human_score']}/100（口径对齐朱雀/墨尺：≥90 达标 / 80-89 警告 / "
          f"<80 需改写；本地启发式，定位与复测基线用）")
    print(f"[i] 维度分（0-100，越低越要改）：句法 {dims['句法']} | 节奏 {dims['节奏']} | 人味 {dims['人味']}")
    print(f"[i] 字数={metrics['chars']}；句长波动={metrics['sent_sd']:.1f}；段长波动={metrics['para_sd']:.1f}；"
          f"单句成段={metrics['one_liners']}；无引号内心戏={metrics['inner_voice']}")
    print(f"[i] 比喻词密度={metrics['simile_per_k']:.1f}/千字；情绪词密度={metrics['emotion_per_k']:.1f}/千字；"
          f"平均每段={metrics['avg_sentences_per_paragraph']:.1f}句；5-gram自重复率={metrics['dup5_pct']}%")
    if reasons:
        print("[!] 触发指标：" + "；".join(reasons))
    hint = weak_dim_hint(dims)
    if hint:
        print(f"[!] {hint}")
    if not reasons and not hint:
        print("[✓] 未触发当前启发式指标")
    print("[i] 这是本地启发式初筛，不替代墨尺或朱雀的模型结论。")
    return 0


def check(path, wmin, wmax, quote_mode="chal", dialog_min=DIALOG_MIN_DEFAULT, dialog_max=DIALOG_MAX_DEFAULT, wall_hard=None, wall_warn=None, chapter_index=None):
    if wall_hard is None:
        wall_hard = config.WALL_HARD  # 延迟绑定：支持运行时覆盖（v7.34 config 传播）
    if wall_warn is None:
        wall_warn = config.WALL_WARN
    if wmin < 0 or wmax < wmin:
        print(f"[✗] 输入错误：字数区间无效（min={wmin}, max={wmax}）")
        return 2
    if not 0 <= dialog_min <= 100 or not 0 <= dialog_max <= 100:
        print(f"[✗] 输入错误：对话占比阈值必须在 0-100（min={dialog_min}, max={dialog_max}）")
        return 2
    if dialog_max and dialog_min < 55 and dialog_min > dialog_max:
        print(f"[✗] 输入错误：对话下限不能高于上限（min={dialog_min}, max={dialog_max}）")
        return 2
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
    # v7.47：剥 `#` 前缀后再匹配——此前用原始行匹配而 TITLE_RE 要求「第」开头，
    # markdown 文件 `# 第1章 风起` 恒不匹配 → 第13项静默跳过 + 误报警告
    title_lines = [ln.strip() for ln in text.splitlines()
                   if TITLE_RE.match(ln.strip().lstrip("#").lstrip())]
    title, t_len = "", 0
    if title_lines:
        if len(title_lines) > 1:
            warnings.append(f"检测到 {len(title_lines)} 个标题行——仅首个作为章节题剔除，其余按正文参与全部校验，请核查是否混入「第X章」行")
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

    # ── 0 前3章开篇闸门（v7.40，黄金开篇铁律：推荐位生死线）──
    if chapter_index is not None and 1 <= chapter_index <= OPENING_GATE_CHAPTERS:
        opening_gate(body, lines, dialogue_span_re(quote_mode), chapter_index, failures, warnings)
        task_maps = {
            1: "主角出场 + 异常事件/核心冲突亮相 + 金手指或悬念露头（AI 语义核验）",
            2: "金手指第一次小规模演示 + 近期目标确立 + 第一个爽点或打脸预告（AI 语义核验）",
            3: "第一个完整爽点闭环（打脸/收益），读者拿到第一次满足（AI 语义核验）",
        }
        print(f"[i] 前三章任务表（第{chapter_index}章）：{task_maps[chapter_index]}")
    elif chapter_index is not None and chapter_index > OPENING_GATE_CHAPTERS:
        print(f"[i] 第{chapter_index}章 > 前{OPENING_GATE_CHAPTERS}章，开篇闸门未启用")

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
    elif dialog_min < 55 and dialog_max and ratio > dialog_max - 5:
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

    # ── 9 排版（文字墙：>wall_hard 硬卡 + (wall_warn, wall_hard] 警告；默认 140/100=config 真源，说书体等题材例外传 --wall 200）──
    para_lens = [count_chars(ln) for ln in lines]
    walls = [(i + 1, n) for i, n in enumerate(para_lens) if n > wall_hard]
    walls_warn = [(i + 1, n) for i, n in enumerate(para_lens) if wall_warn < n <= wall_hard]
    if walls:
        worst = max(walls, key=lambda x: x[1])
        failures.append(f"文字墙：{len(walls)} 个段落超{wall_hard}字（最长第{worst[0]}段 {worst[1]} 字）——手机端必须短段，热榜主流≤90")
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


    # ── v7.49 量化 AI 味硬指标（对标 chinese-novelist-skill 量化口径；警告级，非硬卡）──
    # 口径说明：这两项是「定向改写的线索」而非硬门槛——误伤成本高于收益，
    # 因此只告警不进 failures；作者过一眼决定改不改。
    contrast_n = count_contrast_patterns(body)
    if contrast_n > AI_TASTE_CONTRAST_MAX:
        warnings.append(
            f"「不是A是B」句式 {contrast_n} 处（>{AI_TASTE_CONTRAST_MAX} 处/章）"
            f"——AI 结构指纹最密的一类；改写时直接陈述事实，砍掉否定-肯定对举"
        )
    else:
        print(f"[✓] 「不是A是B」句式 {contrast_n} 处（≤{AI_TASTE_CONTRAST_MAX} 处/章）")
    if total:
        imagery_limit = max(1, total // 1000 * AI_TASTE_IMAGERY_MAX_PER_K)
        repeated = count_repeated_imagery(body)
        over = [(w, n) for w, n in repeated if n > imagery_limit]
        if over:
            detail = "、".join(f"「{w}」×{n}" for w, n in over[:5])
            warnings.append(
                f"单一意象超频（限额 {imagery_limit} 次/千字）：{detail}"
                f"——同一意象反复用会显出模板感；换具体意象或直接删比喻"
            )
        else:
            print(f"[✓] 单一意象无超频（限额 {imagery_limit} 次/千字）")

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

    # ── 警告级：对话三症状机械线索（v7.40，供第20项 AI 语义复核取证）──
    dialogue_symptom_checks(body, lines, span_re, warnings)

    # ── 警告级：高频二字词近距离复用 ──
    # v7.47：先过滤再取 Top8——此前 most_common(8) 先截断，白名单词霸榜挤掉真实候选
    hanzi_only = "".join(ch for ch in body if HANZI.match(ch))
    grams = Counter(hanzi_only[i:i + 2] for i in range(len(hanzi_only) - 1))
    hot = [(w, n) for w, n in grams.most_common()
           if n >= 8 and w not in BIGRAM_WHITELIST and not (w[0] == w[1])][:8]
    if hot:
        warnings.append("高频词疑似复用: " + "、".join(f"「{w}」×{n}" for w, n in hot) + "——查是否同词近距离重复")

    # ── 信息级：AI味指数（粗测，0-10，越高越要人工过目）+ 百分制三维（v7.40）──
    score, reasons, ai_metrics = ai_lite_score(body, lines)
    print(f"[i] AI味指数(粗测) = {score}/10" + ("：" + "；".join(reasons) if reasons else "，机器指标均正常"))
    _dims = ai_metrics["dims"]
    _sample_note = "（样本<800字，三维仅供参考）" if ai_metrics["chars"] < 800 else ""
    print(f"[i] 人类分(粗测) = {ai_metrics['human_score']}/100（句法{_dims['句法']}/节奏{_dims['节奏']}/人味{_dims['人味']}，"
          f"≥90 达标 / 80-89 警告 / <80 需改写）{_sample_note}")
    if score >= AI_SCORE_HARD_MAX:
        failures.append(f"AI味指数 {score}/10 ≥ {AI_SCORE_HARD_MAX}（按《去AI味》8 Gate 定向改写后重测）")
    else:
        _hint = weak_dim_hint(_dims)
        if _hint:
            print(f"[!] {_hint}")

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
        description=f"章节机械校验 v{SKILL_VERSION}（30项中的脚本13项，含章节名规范）",
        epilog="--quote 决定引号违规检测与对话占比统计用哪套引号，二者同源；"
               "--dialog-min/--dialog-max 默认 15/50（v7.19 热榜实证 10-49%%；>=55 剧本口径自动豁免上限）。")
    ap.add_argument("file")
    ap.add_argument("--min", type=int, default=None, help=f"字数下限（默认{DEFAULT_CHAPTER_MIN}；--platform 预设可整体切换）")
    ap.add_argument("--max", type=int, default=None, help=f"字数上限（默认{DEFAULT_CHAPTER_MAX}；--platform 预设可整体切换）")
    ap.add_argument("--quote", choices=QUOTE_MODES, default="chal",
                    help="引号口径：chal(默认,中文弯引号) / straight(半角双引号,短篇) / any(容错)")
    ap.add_argument("--dialog-min", type=int, default=None, dest="dialog_min",
                    help="对话占比硬卡下限%%（默认15；15-25警告；短剧剧本传60，>=55时自动豁免上限检查；--platform 预设可整体切换）")
    ap.add_argument("--dialog-max", type=int, default=None, dest="dialog_max",
                    help="对话占比上限%%（默认50，热榜实证；传0关闭；--platform 预设可整体切换）")
    ap.add_argument("--platform", choices=sorted(config.PLATFORM_PRESETS), default=None,
                    help="平台预设（v7.40）：fanqie默认/qidian/jinjiang/qimao/zongheng/feilu——切字数带与对话区间，"
                         "取值真源=references/平台参数表.md；显式 --min/--max/--dialog-* 优先于预设")
    ap.add_argument("--wall", type=int, default=WALL_HARD, dest="wall_hard",
                    help=f"文字墙硬卡阈值%%（默认{WALL_HARD}=config真源；说书体/古言等长段题材经书格传 200）")
    ap.add_argument("--wall-warn", type=int, default=WALL_WARN, dest="wall_warn",
                    help=f"长段警告阈值%%（默认{WALL_WARN}；须小于 --wall）")
    ap.add_argument("--ai-lite", action="store_true",
                    help="只跑零依赖 AI 味粗测（百分制人类分+句法/节奏/人味三维短板），不执行完整章节硬卡")
    ap.add_argument("--chapter-index", type=int, default=None, dest="chapter_index",
                    help=f"章节序号（1起）。N≤{OPENING_GATE_CHAPTERS} 启用前3章开篇闸门（禁开头8条+前300字人物异常+前3段钩子）；"
                         f"未传参时自动从标题行「第N章」推断")
    args = ap.parse_args()
    if args.ai_lite:
        sys.exit(ai_lite_check(args.file))
    # 参数优先级（v7.40）：显式 --min/--max/--dialog-* > --platform 预设 > config 默认
    preset = config.PLATFORM_PRESETS.get(args.platform or "", {})
    wmin = args.min if args.min is not None else preset.get("chapter_min", DEFAULT_CHAPTER_MIN)
    wmax = args.max if args.max is not None else preset.get("chapter_max", DEFAULT_CHAPTER_MAX)
    dmin = args.dialog_min if args.dialog_min is not None else preset.get("dialog_min", DIALOG_MIN_DEFAULT)
    dmax = args.dialog_max if args.dialog_max is not None else preset.get("dialog_max", DIALOG_MAX_DEFAULT)
    if args.platform:
        print(f"[i] 平台预设 {args.platform}：字数 {wmin}-{wmax}，对话 {dmin}-{dmax}（真源=references/平台参数表.md）")
    idx = args.chapter_index
    if idx is None:
        try:
            text_for_idx = load_text(args.file)
        except OSError:
            text_for_idx = ""
        idx = infer_chapter_index(text_for_idx)
        if idx is not None and 1 <= idx <= OPENING_GATE_CHAPTERS:
            print(f"[i] 未传 --chapter-index，已从标题行推断为第{idx}章，启用开篇闸门")
    sys.exit(check(args.file, wmin, wmax, args.quote, dmin, dmax, args.wall_hard, args.wall_warn, idx))


if __name__ == "__main__":
    main()
