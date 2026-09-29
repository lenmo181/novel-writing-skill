# -*- coding: utf-8 -*-
"""检查技能包的版本、默认值、路径和关键引用是否一致。"""
from pathlib import Path
import re
import sys

from config import (
    DEFAULT_AI_SCORE_HARD_MAX,
    DEFAULT_CHAPTER_MAX,
    DEFAULT_CHAPTER_MIN,
    DEFAULT_CONTEXT_MAX_CHARS,
    DEFAULT_CONTEXT_RECENT_CHAPTERS,
    DEFAULT_DIALOG_MAX,
    DEFAULT_DIALOG_MIN,
    DEFAULT_DIFF_DELETE_WARN,
    DEFAULT_MOCHI_FLOOR,
    DEFAULT_MOCHI_MIN,
    DEFAULT_ZHUQUE_THRESHOLD,
    DEFAULT_ZHUQUE_WARN,
    SKILL_VERSION,
    RELEASE_DATE,
    TITLE_MAX,
    TITLE_MIN,
)


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    """读技能包内文件；缺失/占用时返回空串记为一条错误，不让单个文件缺失
    把整个 lint 变成裸 traceback（v7.30）。"""
    try:
        return (ROOT / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def fail(errors, message):
    errors.append(message)


def main() -> int:
    errors = []
    for core in ("SKILL.md", "README.md", "references/常量表.md"):
        if not (ROOT / core).is_file():
            errors.append(f"核心文件缺失：{core}")
    skill = read("SKILL.md")
    readme = read("README.md")
    constants = read("references/常量表.md")
    if not skill or not readme or not constants:
        # 依赖文件不全时后面的逐项内容检查全部会误报，直接返回
        for m in errors:
            print(f"[✗] {m}")
        return 1

    if f"v{SKILL_VERSION}" not in skill.split("## 📚 版本历史", 1)[0]:
        fail(errors, f"SKILL.md 活跃正文缺少 v{SKILL_VERSION}")
    if f"v{SKILL_VERSION}" not in readme.split("## 版本历史", 1)[0]:
        fail(errors, f"README.md 活跃正文缺少 v{SKILL_VERSION}")
    if RELEASE_DATE not in skill.split("## 📚 版本历史", 1)[0]:
        fail(errors, f"SKILL.md 活跃正文缺少发布日 {RELEASE_DATE}")
    if RELEASE_DATE not in readme.split("## 版本历史", 1)[0]:
        fail(errors, f"README.md 活跃正文缺少发布日 {RELEASE_DATE}")
    desc = re.search(r"description: \"(.*?)\"", skill, re.S)
    if desc is None:
        fail(errors, "frontmatter description 未找到（需 description: \"…\" 双引号格式）")
    elif len(desc.group(1)) > 320:
        fail(errors, "frontmatter description 过长，超过 320 字符")

    checks = {
        "章节下限": (str(DEFAULT_CHAPTER_MIN), skill, constants),
        "章节上限": (str(DEFAULT_CHAPTER_MAX), skill, constants),
        "对话下限": (str(DEFAULT_DIALOG_MIN), skill, constants),
        "对话上限": (str(DEFAULT_DIALOG_MAX), skill, constants),
        "AI味硬线": (str(DEFAULT_AI_SCORE_HARD_MAX), skill, constants),
        "标题下限": (str(TITLE_MIN), skill, constants),
        "标题上限": (str(TITLE_MAX), skill, constants),
    }
    for label, (value, *docs) in checks.items():
        if not all(value in doc for doc in docs):
            fail(errors, f"{label}未同时出现在主规则和常量表")

    fusion_checks = {
        "上下文最近章节数": str(DEFAULT_CONTEXT_RECENT_CHAPTERS),
        "上下文单文件预算": str(DEFAULT_CONTEXT_MAX_CHARS),
        "改稿删除比例预警": f"{DEFAULT_DIFF_DELETE_WARN:.0%}",
    }
    for label, value in fusion_checks.items():
        if value not in constants:
            fail(errors, f"{label}未出现在常量表")

    for path in ["tools/check_chapter.py", "tools/zhuque_check.py", "tools/mochi_check.py",
                 "tools/cover_check.py", "tools/visualize.py", "tools/gen_index.py",
                 "tools/project_audit.py", "tools/continuity_check.py", "tools/context_pack.py",
                 "tools/chapter_diff.py", "tools/snapshot_project.py", "tools/update_skill.py",
                 "tools/doctor.py", "tools/eval_skill.py", "tools/release_check.py",
                 "tools/init_project.py", "tools/entity_index.py", "tools/project_health.py"]:
        text = read(path)
        if f"v{SKILL_VERSION}" not in text[:1200]:
            fail(errors, f"{path} 头部未标注技能版本 v{SKILL_VERSION}")

    # 活跃文档不得继续绑定某一用户或旧部署目录；版本历史可保留历史记录。
    active_docs = {
        "SKILL.md": skill.split("## 📚 版本历史", 1)[0],
        "README.md": readme.split("## 版本历史", 1)[0],
        "references/无人值守.md": read("references/无人值守.md"),
        "references/封面.md": read("references/封面.md"),
        "references/开源融合.md": read("references/开源融合.md"),
        "references/快速开始.md": read("references/快速开始.md"),
        "references/操作范例.md": read("references/操作范例.md"),
        "references/模式操作卡.md": read("references/模式操作卡.md"),
        "references/评测场景.md": read("references/评测场景.md"),
        "references/评测量表.md": read("references/评测量表.md"),
        "references/回执协议.md": read("references/回执协议.md"),
        "references/常见问题.md": read("references/常见问题.md"),
        "templates/项目模板.md": read("templates/项目模板.md"),
    }
    for path, text in active_docs.items():
        if ".zcode" in text or "C:\\Users\\lenmo" in text:
            fail(errors, f"{path} 仍含用户绑定或旧部署路径")

    # 关键默认值必须由配置模块驱动，而不是再次硬编码 argparse 默认值。
    tool_text = read("tools/check_chapter.py")
    if "default=2000" in tool_text or "default=2500" in tool_text:
        fail(errors, "check_chapter.py 仍直接硬编码章节默认值")
    if "default=90" in read("tools/zhuque_check.py") or "default=80" in read("tools/zhuque_check.py"):
        fail(errors, "zhuque_check.py 仍直接硬编码阈值默认值")
    if "default=9" in read("tools/mochi_check.py") or "default=8" in read("tools/mochi_check.py"):
        fail(errors, "mochi_check.py 仍直接硬编码阈值默认值")

    if errors:
        for error in errors:
            print(f"[✗] {error}")
        print(f"结论：技能 lint 失败（{len(errors)} 项）")
        return 1
    print(f"[✓] 网络小说创作技能 v{SKILL_VERSION} lint 通过")
    print(f"[i] 关键默认值：字数 {DEFAULT_CHAPTER_MIN}-{DEFAULT_CHAPTER_MAX}；对话 {DEFAULT_DIALOG_MIN}-{DEFAULT_DIALOG_MAX}；朱雀 {DEFAULT_ZHUQUE_THRESHOLD}/{DEFAULT_ZHUQUE_WARN}；墨尺 {DEFAULT_MOCHI_MIN}/{DEFAULT_MOCHI_FLOOR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
