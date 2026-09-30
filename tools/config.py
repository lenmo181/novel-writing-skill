# -*- coding: utf-8 -*-
"""网络小说创作技能的程序级真源配置。

Markdown 手册负责解释规则；脚本默认值统一从这里读取，避免版本升级时
出现“文档一套、CLI 一套”的漂移。
"""
from pathlib import Path
import os


SKILL_VERSION = "7.35"
# 版本发布/SkillHub 上线日期；不要使用研发开始日期替代。
RELEASE_DATE = "2026-09-30"

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
DEFAULT_DIFF_DELETE_WARN = 0.10

TITLE_MIN = 2
TITLE_MAX = 12

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
