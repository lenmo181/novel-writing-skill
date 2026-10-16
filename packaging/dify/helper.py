#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dify 插件共享工具：定位随插件分发的技能脚本目录。

插件在 Dify 沙箱内运行，**拿不到用户本地磁盘路径**，
因此所有工具都以「正文文本」为输入，落临时文件后再跑校验脚本。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent

# 与 MCP Server 一致的只读白名单
READONLY_TOOLS = (
    "check_chapter.py",
    "chapter_readiness.py",
    "conflict_score.py",
    "continuity_check.py",
    "review_skeleton.py",
    "project_audit.py",
    "project_health.py",
    "grep_consistency.py",
    "entity_index.py",
    "research_audit.py",
    "retention_check.py",
    "cover_check.py",
    "script_check.py",
    "chapter_diff.py",
    "check_refs.py",
    "lint_skill.py",
    "eval_skill.py",
    "doctor.py",
    "export_assistant_txt.py",
)

DEFAULT_TIMEOUT = 120


def scripts_dir() -> Path:
    """脚本目录：插件内 `_skill/tools` → 环境变量覆盖 → 源码仓库 `tools/`。"""
    bundled = PLUGIN_ROOT / "_skill" / "tools"
    if bundled.is_dir():
        return bundled
    env = os.environ.get("NOVEL_SKILL_SCRIPTS", "").strip()
    if env:
        return Path(env).expanduser()
    return PLUGIN_ROOT.parent.parent / "tools"


def skill_root() -> Path:
    bundled = PLUGIN_ROOT / "_skill"
    if bundled.is_dir():
        return bundled
    env = os.environ.get("NOVEL_SKILL_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return PLUGIN_ROOT.parent.parent


def run_validator(script: str, args: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """运行白名单内的只读脚本，返回 {exit_code, stdout, stderr} 或 {error}。"""
    if script not in READONLY_TOOLS:
        return {"error": "脚本 %s 不在只读白名单内，拒绝执行" % script}
    target = scripts_dir() / script
    if not target.is_file():
        return {"error": "脚本不存在：%s（插件未打包技能？跑一下 bundle_skill.py）" % target}
    try:
        proc = subprocess.run(
            [sys.executable, str(target), *args],
            cwd=str(skill_root()),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": "脚本执行超时（%ss）：%s" % (timeout, script)}
    except OSError as exc:
        return {"error": "脚本启动失败：%s" % exc}
    return {
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def run_validator_on_text(script: str, text: str, extra_args: list[str] | None = None,
                          suffix: str = ".md") -> dict:
    """把正文写入临时文件后跑校验脚本（Dify 场景：只有文本，没有本地路径）。"""
    if not text or not text.strip():
        return {"error": "正文为空"}
    tmp_dir = Path(tempfile.mkdtemp(prefix="novel_dify_"))
    target = tmp_dir / ("chapter" + suffix)
    try:
        target.write_text(text, encoding="utf-8")
        return run_validator(script, [str(target), *(extra_args or [])])
    finally:
        for p in sorted(tmp_dir.glob("*")):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
