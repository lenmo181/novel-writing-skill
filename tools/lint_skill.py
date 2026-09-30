# -*- coding: utf-8 -*-
"""技能包版本治理检查器（v7.36）：检查版本真源、默认值、路径、规则台账和运行时手册。"""
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
    FULL_REVIEW_DIALOG_MAX,
    FULL_REVIEW_FORESHADOW_T2,
    FULL_REVIEW_FORESHADOW_T3,
    FULL_REVIEW_LENGTH_HIGH_RATIO,
    FULL_REVIEW_LENGTH_LOW_RATIO,
    FULL_REVIEW_LENGTH_MIN_MEDIAN,
    FULL_REVIEW_NGRAM_OVERLAP_WARN,
    FULL_REVIEW_RHYTHM_BUFFER_STREAK,
    FULL_REVIEW_RHYTHM_SAME_STREAK,
    SKILL_VERSION,
    RELEASE_DATE,
    TITLE_MAX,
    TITLE_MIN,
    WALL_HARD,
    WALL_WARN,
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

    # 工具版本治理：当前运行/治理工具必须标当前版本；稳定工具若有历史版本标记，不因补丁版升级强制重写。
    pinned_tools = {
        "tools/full_review.py", "tools/lint_skill.py", "tools/repair_runner.py",
    }
    tool_paths = [
        "tools/check_chapter.py", "tools/zhuque_check.py", "tools/mochi_check.py",
        "tools/cover_check.py", "tools/visualize.py", "tools/gen_index.py",
        "tools/project_audit.py", "tools/continuity_check.py", "tools/context_pack.py",
        "tools/chapter_diff.py", "tools/snapshot_project.py", "tools/update_skill.py",
        "tools/doctor.py", "tools/eval_skill.py", "tools/release_check.py",
        "tools/init_project.py", "tools/entity_index.py", "tools/project_health.py",
        "tools/full_review.py", "tools/lint_skill.py", "tools/repair_runner.py",
    ]
    for path in tool_paths:
        text = read(path)
        if path in pinned_tools and f"v{SKILL_VERSION}" not in text[:1200]:
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
        "references/规则台账.md": read("references/规则台账.md"),
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


    # ── v7.35 规则治理六检 ──
    # 1) 规则台账完整性：RB 行数、字段对齐、状态枚举、执行工具/对应测试列必须有内容
    ledger = read("references/规则台账.md")
    rb_rows = [m.group(0) for m in re.finditer(r"^\| RB-\d{3} \|.*$", ledger, re.M)]
    if len(rb_rows) < 25:
        fail(errors, f"规则台账 RB 条目不足（{len(rb_rows)} < 25）")
    ids = [r.split("|")[1].strip() for r in rb_rows]
    if len(ids) != len(set(ids)):
        fail(errors, "规则台账 RB 编号重复")
    for r in rb_rows:
        cells = [c.strip() for c in r.split("|")[1:-1]]
        if len(cells) != 11:
            fail(errors, f"规则台账行字段数异常（应为11列）：{r[:40]}…")
            break
        if cells[7] not in ("候选", "实验", "稳定", "修正", "废弃"):
            fail(errors, f"规则台账状态枚举非法：{cells[0]}={cells[7]}")
            break
        if not cells[4] or not cells[5] or not cells[6] or not cells[8] or not cells[9] or not cells[10]:
            fail(errors, f"规则台账缺最近/验证广度/证据等级/落点/执行工具/对应测试：{cells[0]}")
            break

    # 1b) 核心30项注册表：每项必须恰好一行，且绑定登记ID、执行器、测试入口。
    core_map = read("references/核心校验映射.md")
    map_rows = [x for x in core_map.splitlines() if re.match(r"^\| \d+ \|", x)]
    if not core_map:
        fail(errors, "核心校验映射缺失：references/核心校验映射.md")
    if len(map_rows) != 30:
        fail(errors, f"核心校验映射条目数异常：{len(map_rows)} / 30")
    map_nums = []
    for row in map_rows:
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) != 7:
            fail(errors, f"核心校验映射字段数异常：{row[:50]}…")
            continue
        try:
            num = int(cells[0])
            map_nums.append(num)
        except ValueError:
            fail(errors, f"核心校验映射项目号非法：{cells[0]}")
            continue
        if not cells[3] or not cells[4] or not cells[5]:
            fail(errors, f"核心校验映射缺登记ID/执行器/测试：第{num}项")
    if sorted(map_nums) != list(range(1, 31)):
        fail(errors, f"核心校验映射必须覆盖1-30且各一次：{sorted(map_nums)}")

    # 2) 常量完整性：config 的墙/审稿常量必须在常量表有同值记载
    const_text = read("references/常量表.md")
    const_expect = [
        (str(WALL_HARD), "WALL_HARD"), (str(WALL_WARN), "WALL_WARN"),
        (f"{FULL_REVIEW_LENGTH_HIGH_RATIO}", "FULL_REVIEW_LENGTH_HIGH_RATIO"),
        (f"{FULL_REVIEW_LENGTH_LOW_RATIO}", "FULL_REVIEW_LENGTH_LOW_RATIO"),
        (str(FULL_REVIEW_DIALOG_MAX), "FULL_REVIEW_DIALOG_MAX"),
        (str(FULL_REVIEW_NGRAM_OVERLAP_WARN), "FULL_REVIEW_NGRAM_OVERLAP_WARN"),
        (str(FULL_REVIEW_FORESHADOW_T2), "FULL_REVIEW_FORESHADOW_T2"),
        (str(FULL_REVIEW_FORESHADOW_T3), "FULL_REVIEW_FORESHADOW_T3"),
    ]
    for value, name in const_expect:
        if value not in const_text:
            fail(errors, f"常量表未记载 config 值 {name}={value}（真源漂移）")

    # 3) 工具映射：常量表引用的 tools/*.py 必须存在
    for m in set(re.findall(r"tools/([a-z_]+\.py)", const_text)):
        if not (ROOT / "tools" / m).is_file():
            fail(errors, f"常量表引用的工具不存在：tools/{m}")

    # 4) 测试映射：治理回归测试必须存在
    for tf in ("test_v733_upgrade.py", "test_v734_governance.py", "test_v735_governance.py", "test_v736_governance.py"):
        if not (ROOT / "tests" / tf).is_file():
            fail(errors, f"治理测试缺失：tests/{tf}")

    # 5) 运行时手册版本台账：实际 references/*.md 必须全部登记且统一指向当前版本。
    manifest_path = "references/版本台账.md"
    manifest = read(manifest_path)
    actual_manuals = {str(p.relative_to(ROOT)) for p in (ROOT / "references").glob("*.md")}
    manifest_rows = re.findall(r"^\| (references/[^|]+\.md) \| (v\d+\.\d+(?:\.\d+)?) \| ([^|]+) \|$", manifest, re.M)
    manifest_paths = [row[0] for row in manifest_rows]
    if not manifest:
        fail(errors, f"运行时版本台账缺失：{manifest_path}")
    if len(manifest_paths) != len(set(manifest_paths)):
        fail(errors, "运行时版本台账存在重复路径")
    if set(manifest_paths) != actual_manuals:
        missing = sorted(actual_manuals - set(manifest_paths))
        stale = sorted(set(manifest_paths) - actual_manuals)
        if missing:
            fail(errors, f"运行时版本台账漏登记：{missing}")
        if stale:
            fail(errors, f"运行时版本台账存在悬空路径：{stale}")
    for path, version, _category in manifest_rows:
        if version != f"v{SKILL_VERSION}":
            fail(errors, f"运行时手册版本漂移：{path}={version}，当前应为 v{SKILL_VERSION}")
    if manifest and len(manifest_rows) != len(actual_manuals):
        fail(errors, f"运行时版本台账条目数异常：{len(manifest_rows)} / {len(actual_manuals)}")

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
