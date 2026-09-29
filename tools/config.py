# -*- coding: utf-8 -*-
"""网络小说创作技能的程序级真源配置。

Markdown 手册负责解释规则；脚本默认值统一从这里读取，避免版本升级时
出现“文档一套、CLI 一套”的漂移。
"""
from pathlib import Path
import os


SKILL_VERSION = "7.32"
# 版本发布/SkillHub 上线日期；不要使用研发开始日期替代。
RELEASE_DATE = "2026-09-29"

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
