# -*- coding: utf-8 -*-
"""网络小说创作技能的程序级真源配置。

Markdown 手册负责解释规则；脚本默认值统一从这里读取，避免版本升级时
出现“文档一套、CLI 一套”的漂移。
"""
from pathlib import Path
import os


SKILL_VERSION = "7.50"
# 版本发布/SkillHub 上线日期；不要使用研发开始日期替代。
RELEASE_DATE = "2026-10-25"

SKILLHUB_SLUG = "@user_cd8383ec/web-novel-writing"
SKILLHUB_DOWNLOAD_URL = (
    "https://api.skillhub.cn/api/v1/download?slug=@user_cd8383ec/web-novel-writing"
)

DEFAULT_CHAPTER_MIN = 2000
DEFAULT_CHAPTER_MAX = 2500
DEFAULT_DIALOG_MIN = 15
DEFAULT_DIALOG_MAX = 50
DEFAULT_AI_SCORE_HARD_MAX = 6

DEFAULT_ZHUQUE_THRESHOLD = 90
DEFAULT_ZHUQUE_WARN = 80
DEFAULT_MOCHI_MIN = 9
DEFAULT_MOCHI_FLOOR = 8

DEFAULT_CONTEXT_RECENT_CHAPTERS = 3
DEFAULT_CONTEXT_MAX_CHARS = 6000
# 上下文包总预算（v7.45）：单文件上限之外再加一道总量闸门，
# 保证 1000+ 章时上下文不会随 recent 线性膨胀。权重见 context_pack.ROLE_WEIGHTS。
DEFAULT_CONTEXT_MAX_TOTAL = 24000
# 当前章的保底份额：预算再紧也不低于总量的这个比例（否则写作者看不到本章原文）
DEFAULT_CONTEXT_CURRENT_FLOOR_RATIO = 0.25
DEFAULT_DIFF_DELETE_WARN = 0.10

TITLE_MIN = 2
TITLE_MAX = 12

# 前3章开篇闸门（v7.40；真源=常量表·三C，《写作铁律.md·黄金开篇铁律》）
OPENING_GATE_CHAPTERS = 3   # 第 N≤3 章启用开篇专项
OPENING_WINDOW_CHARS = 300  # 「前300字手术标准」检测窗口（可计数字符）
OPENING_PARAS = 3           # 「开篇三句入戏」检测段数（前3段钩子信号≥1）

# 平台参数预设（v7.40；人读真源=references/平台参数表.md，含证据等级）
# 只收脚本可执行的硬参数：字数带与对话区间；章名/付费节点/封面属人读字段。
PLATFORM_PRESETS = {
    "fanqie": {"chapter_min": 2000, "chapter_max": 2500, "dialog_min": 15, "dialog_max": 50},
    "qidian": {"chapter_min": 2000, "chapter_max": 4000, "dialog_min": 15, "dialog_max": 50},
    "jinjiang": {"chapter_min": 2000, "chapter_max": 3000, "dialog_min": 20, "dialog_max": 55},
    "qimao": {"chapter_min": 2000, "chapter_max": 2500, "dialog_min": 15, "dialog_max": 50},
    "zongheng": {"chapter_min": 2500, "chapter_max": 3500, "dialog_min": 12, "dialog_max": 45},
    "feilu": {"chapter_min": 2000, "chapter_max": 3000, "dialog_min": 20, "dialog_max": 55},
}
PLATFORM_ALIASES = {
    "番茄": "fanqie", "起点": "qidian", "晋江": "jinjiang",
    "七猫": "qimao", "纵横": "zongheng", "飞卢": "feilu",
}

# 文字墙（v7.34 收敛为唯一真源；题材/书格例外经 check_chapter.py --wall 覆盖）
WALL_HARD = 140          # > 140 硬卡
WALL_WARN = 100          # (WALL_WARN, WALL_HARD] 警告

# 全文审稿流水线阈值（v7.34 起唯一真源；常量表·十三与此一致，由 lint/测试守护）
FULL_REVIEW_NGRAM_OVERLAP_WARN = 40     # 相邻章 3-gram 重复率 %（与留存分析同源）
FULL_REVIEW_DIALOG_MAX = 55             # 小说体对话占比告警 %
FULL_REVIEW_LENGTH_HIGH_RATIO = 1.6     # 字数 > 书内中位 ×1.6 → P2
FULL_REVIEW_LENGTH_TOP_RATIO = 2.0      # 字数 > 书内中位 ×2.0 → P1
FULL_REVIEW_LENGTH_LOW_RATIO = 0.55     # 字数 < 书内中位 ×0.55 → P2
FULL_REVIEW_LENGTH_MIN_MEDIAN = 1500    # 书内中位低于此值不启用字数偏离检查
FULL_REVIEW_FORESHADOW_T2 = 40          # Tier-2 伏笔沉睡阈值（章）
FULL_REVIEW_FORESHADOW_T3 = 20          # Tier-3 伏笔沉睡阈值（章）
FULL_REVIEW_RHYTHM_SAME_STREAK = 3      # 同节奏类型连续 ≥3 章告警
FULL_REVIEW_RHYTHM_BUFFER_STREAK = 4    # 缓冲型合计连续 ≥4 章告警

# 期待线悬空阈值（v7.49 补齐）
# 背景：v7.40 引入期待线台账 + 悬空告警时，此常量只写了引用点（continuity_check.py）
# 未在 config.py 定义——只要项目的 mind/期待线.md 存在「活跃」状态条目，
# continuity_check.py 即 NameError 崩溃，整条连续性检查链（含 chapter_readiness
# 工程 Gate）全部中断。v7.49 起提到 config.py 作为真源，并纳入 lint 漂移守护。
EXPECTATION_STALE_CHAPTERS = 8          # 活跃期待线最近推进章距当前最新章超过此值 = 悬空

# 事实台账（v7.49）：对标 chinese-novelist-skill「设定与事实词典」与
# AI_NovelGenerator entity_state_history。先登记后写、到期必兑、数字事实优先登记。
FACT_LEDGER_DUE_OFFSET = 3              # 事实到期章 = 登记章 + 此偏移；≤0 表示不设到期
FACT_LEDGER_DIGIT_MIN_LEN = 2           # 数字事实判定：抽取连续数字/中文数字串的最小长度
FACT_LEDGER_MAX_PER_CHAPTER = 12        # 单章未登记数字事实超过此数 = 告警（先登记后写）
FACT_LEDGER_UNKNOWN_REASONS = (         # unknown 位置的合法原因枚举
    "nonexistent",      # 不存在（该事实本就不成立）
    "unclaimed",        # 未认领（尚未指定归属）
    "before_start",     # 早于开书
    "voided",           # 已作废
    "needs_review",     # 待复核
    "unresolved_reference",  # 引用未解析
)
FACT_LEDGER_POSITIONS = (              # 事实位置语义枚举
    "book_start",       # 开书即成立
    "volume_start",     # 某卷开始成立
    "chapter_before",   # 某章之前成立
    "chapter_after",    # 某章之后成立
    "unknown",          # 位置未知（须在 unknown_reason 列说明原因）
)
FACT_LEDGER_STATUSES = (               # 事实状态枚举
    "已登记",           # 已登记未兑现
    "已兑现",           # 已在正文落地
    "待回收",           # 承诺后续章节兑现
    "已作废",           # 明确废弃
    "不适用",           # 非正文事实（如设定参数）
)

# 伏笔到期提醒（v7.49）：对标 MuMuAINovel 三层提醒（必须回收 / 已超期 / 近期待回收）
FORESHADOW_DUE_OFFSET = 3              # 预计回收章 ≤ 当前最新章 + 此值 = 近期待回收
FORESHADOW_OVERDUE_OFFSET = 5          # 预计回收章 ≤ 当前最新章 - 此值 = 已超期
FORESHADOW_STATUSES = (                # 伏笔状态白名单（在原白名单上扩展「部分回收」）
    "未回收", "已回收", "已废弃", "待定", "部分回收", "-",
)

# 量化 AI 味硬指标（v7.49）：对标 chinese-novelist-skill 的量化硬指标口径
# （不是A是B ≤2处/章、单一意象 ≤1次/千字、标志小动作 ≤8次/全书、格言式收尾 ≤3次/全书）。
# 本技能只接「单章可机械判定」的两项；跨章口径（全书级）由 full_review 承担或不做，
# 避免误伤与口径重叠。全部为警告级——量化指标是定向改写的线索，不是硬卡。
AI_TASTE_CONTRAST_MAX = 2             # 「不是A是B」句式上限（处/章），来源：chinese-novelist-skill
AI_TASTE_IMAGERY_MAX_PER_K = 1        # 单一意象上限（次/千字），来源：chinese-novelist-skill
AI_TASTE_IMAGERY_MIN_LEN = 2          # 意象词最小长度（单字不算意象）
# 标志小动作/格言式收尾为全书级口径，本技能暂不做单章判定（见 references/常量表.md 十四）。

PROJECT_ROOT_ENV = "NOVEL_PROJECT_ROOT"


def skill_root() -> Path:
    """返回当前技能包根目录，不依赖用户名称或安装位置。"""
    return Path(__file__).resolve().parents[1]


def default_project_root() -> Path:
    """返回跨平台默认项目根；用户可用 NOVEL_PROJECT_ROOT 覆盖。"""
    explicit = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "workspace" / "novels"


def resolve_project_root(value: str = "") -> Path:
    """优先使用显式参数，其次使用 NOVEL_PROJECT_ROOT，再回退到默认根。"""
    if value and value.strip():
        return Path(value).expanduser()
    return default_project_root()
