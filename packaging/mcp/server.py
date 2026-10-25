#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络小说创作技能 · MCP Server（Model Context Protocol）

把技能包内的机械校验脚本暴露为 MCP 工具，供任意 MCP 宿主
（Claude Code / Cursor / Codex / WorkBuddy 等）调用。

设计约束
--------
- **纯 Python 标准库**，零第三方依赖（与技能包一致的工程约束）
- stdio 传输：JSON-RPC 2.0，每行一条消息
- **只读为主**：本 Server 只调用技能包内的只读校验脚本，
  不修改用户书稿；写盘类脚本（bump_version / init_project / snapshot 等）
  不在白名单内，避免误伤

技能根目录解析顺序
------------------
1. 环境变量 ``NOVEL_SKILL_ROOT``
2. 包内自带 ``_skill/``（wheel 安装模式，见 ``packaging/pypi/``）
3. 本文件上两级目录（``packaging/mcp/`` -> 仓库根）

脚本目录解析顺序
----------------
1. 环境变量 ``NOVEL_SKILL_SCRIPTS``
2. 包内自带 ``_skill/tools`` 或 ``_scripts``（wheel 安装模式）
3. 技能根的 ``tools/`` 或 ``scripts/``

脚本目录命名兼容：源仓库为 ``tools/``，上架包内为 ``scripts/``。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "web-novel-writing"
SERVER_VERSION = "7.52.0"
DEFAULT_TIMEOUT = 300

# 只暴露无默认写盘副作用的脚本；写盘类脚本刻意排除
# v7.47：READMEONLY 语义修正——原 19 项白名单中 export_assistant_txt 默认即写盘
# （无需参数即写 <项目根>/导出/，--out 可写任意路径），已移出本集合（导出请走本地 CLI）。
# 其余脚本中多个支持 --out/--force 任意路径写盘，由 run_script 的参数黑名单兜底
# （见 BANNED_FLAGS）；review_skeleton 默认写 mind/审校/ 是 Gate 流程内标准产物位置，
# 属流程必需，任意路径写入已被黑名单挡住。
READONLY_TOOLS = {
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
    # v7.49：事实台账核验（只读）
    "fact_ledger.py",
    "chapter_brief.py",
    "scene_continuity.py",
}

# v7.47：只读通道参数黑名单——白名单脚本中多个支持 --out/--force 任意路径写盘
# （chapter_readiness/chapter_diff/continuity_check/project_audit/project_health/
# entity_index/research_audit/review_skeleton），
# 经 run_skill_tool 透传即可放大为任意文件写，一律拒绝。
BANNED_FLAGS = {"--out", "--force", "--encoding", "--package-smoke", "--write"}


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def _package_dir() -> Path:
    """本服务器所在目录。wheel 安装后即 ``site-packages/web_novel_writing_mcp/``。"""
    return Path(__file__).resolve().parent


def resolve_skill_root() -> Path:
    env = os.environ.get("NOVEL_SKILL_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    bundled = _package_dir() / "_skill"
    if bundled.is_dir():
        return bundled.resolve()
    return Path(__file__).resolve().parents[2]


def resolve_scripts_dir() -> Path:
    env = os.environ.get("NOVEL_SKILL_SCRIPTS")
    if env:
        return Path(env).expanduser().resolve()
    here = _package_dir()
    for bundled in (here / "_skill" / "tools", here / "_skill" / "scripts",
                    here / "_scripts"):
        if bundled.is_dir():
            return bundled.resolve()
    root = resolve_skill_root()
    for name in ("tools", "scripts"):
        cand = root / name
        if cand.is_dir():
            return cand
    return root / "tools"


def discover_tools() -> list[str]:
    d = resolve_scripts_dir()
    if not d.is_dir():
        return []
    names = [
        p.name
        for p in sorted(d.glob("*.py"))
        if p.name in READONLY_TOOLS and not p.name.startswith("_")
    ]
    return names


# --------------------------------------------------------------------------- #
# 工具定义
# --------------------------------------------------------------------------- #
def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "check_chapter",
        "对单个章节正文跑 30 项校验中的 13 项机械硬卡（字数/格式/对话占比/"
        "AI 味/文字墙/冲突值等）。退出码 1 表示存在硬伤，禁止交付。"
        "参数 path 指向章节 Markdown 文件。",
        {
            "path": {
                "type": "string",
                "description": "章节文件路径，例如 <项目根>/书稿/第001章_开局.md",
            }
        },
        ["path"],
    ),
    _tool(
        "chapter_readiness",
        "章节交付 Gate：校验 30 项校验的语义证据是否齐全"
        "（需 mind/审校/第XXX章审校.json 覆盖第 14-30 项、"
        "并带 status 与 evidence）。full=true 时同时跑全文审稿不落盘模式。",
        {
            "project_root": {"type": "string", "description": "小说项目根目录"},
            "chapter": {"type": "string", "description": "章号，例如 1 或 001"},
            "full": {
                "type": "boolean",
                "description": "是否同时运行全文审稿（默认 false）",
            },
        },
        ["project_root", "chapter"],
    ),
    _tool(
        "doctor",
        "技能安装自检：校验目录骨架、必需文件、版本真源、脚本语法、"
        "相对引用与目录树登记完整性。安装后或排障时先跑它。",
        {},
        [],
    ),
    _tool(
        "list_skill_tools",
        "列出技能包内可供调用的只读校验脚本清单及脚本目录位置。",
        {},
        [],
    ),
    _tool(
        "run_skill_tool",
        "通用入口：运行技能包内任一白名单只读脚本，并返回其退出码与输出。"
        "脚本名取自 list_skill_tools；args 为透传给脚本的参数数组。",
        {
            "script": {
                "type": "string",
                "description": "脚本文件名，如 project_audit.py",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "透传给脚本的命令行参数，例如 [\"<项目根>\"]",
            },
        },
        ["script"],
    ),
]


# --------------------------------------------------------------------------- #
# 执行
# --------------------------------------------------------------------------- #
def run_script(script: str, args: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict:
    scripts_dir = resolve_scripts_dir()
    target = scripts_dir / script
    if script not in READONLY_TOOLS:
        return {"error": "脚本 %s 不在只读白名单内，拒绝执行" % script}
    # v7.47：只读通道参数黑名单（--out=path 形式取 = 前段判断）
    for a in args:
        if a.split("=")[0] in BANNED_FLAGS:
            return {"error": "参数 %s 被拒绝：只读通道不允许写盘参数" % a}
    if not target.is_file():
        return {"error": "脚本不存在：%s" % target}
    try:
        proc = subprocess.run(
            [sys.executable, str(target), *args],
            cwd=str(resolve_skill_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": "脚本执行超时（%ss）：%s" % (timeout, script)}
    except OSError as exc:
        return {"error": "脚本启动失败：%s" % exc}
    # v7.47：stdout 截断到 200KB——full_review --strict 级别的大报告可能撑爆宿主消息尺寸
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    truncated = ""
    if len(stdout) > 200_000:
        stdout, truncated = stdout[:200_000], "（stdout 超 200KB 已截断）"
    return {
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        **({"truncated": truncated} if truncated else {}),
    }


def _text(payload) -> dict:
    return {"content": [{"type": "text", "text": payload}]}


def call_tool(name: str, arguments: dict) -> dict:
    arguments = arguments or {}
    if name == "list_skill_tools":
        tools = discover_tools()
        body = "技能根目录：%s\n脚本目录：%s\n可用只读脚本（%d）：\n%s" % (
            resolve_skill_root(),
            resolve_scripts_dir(),
            len(tools),
            "\n".join("  - " + t for t in tools),
        )
        return _text(body)

    if name == "check_chapter":
        path = str(arguments.get("path", "")).strip()
        if not path:
            raise ValueError("缺少必填参数 path")
        res = run_script("check_chapter.py", [path])
    elif name == "chapter_readiness":
        root = str(arguments.get("project_root", "")).strip()
        chapter = str(arguments.get("chapter", "")).strip()
        if not root or not chapter:
            raise ValueError("缺少必填参数 project_root / chapter")
        args = [root, chapter]
        # v7.47：is True 严格判断——此前 arguments.get("full") 直接判真，
        # LLM 传字符串 "false" 也会启用 --full
        if arguments.get("full") is True:
            args.append("--full")
        res = run_script("chapter_readiness.py", args)
    elif name == "doctor":
        res = run_script("doctor.py", [])
    elif name == "run_skill_tool":
        script = str(arguments.get("script", "")).strip()
        raw_args = arguments.get("args") or []
        if not isinstance(raw_args, list) or not all(
            isinstance(a, str) for a in raw_args
        ):
            raise ValueError("args 必须是字符串数组")
        res = run_script(script, raw_args)
    else:
        raise ValueError("未知工具：%s" % name)

    if "error" in res:
        return {"isError": True, **_text(res["error"])}
    body = "exit_code=%s\n\n%s" % (res["exit_code"], res["stdout"] or "(无输出)")
    if res["stderr"]:
        body += "\n\n[stderr]\n" + res["stderr"]
    out = _text(body)
    if res["exit_code"] != 0:
        out["isError"] = True
    return out


# --------------------------------------------------------------------------- #
# JSON-RPC 主循环
# --------------------------------------------------------------------------- #
def handle(req: dict):
    method = req.get("method")
    params = req.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params.get("name", ""), params.get("arguments") or {})
    if method in ("ping", "logging/setLevel"):
        return {}
    raise KeyError(method)


def main() -> int:
    # v7.47：stdio UTF-8 重配置——此前未 reconfigure，中文 Windows（cp936 locale）下
    # 输出含 ✓/✗（U+2713/2717，GBK 码表外）即 UnicodeEncodeError 杀死整个 Server；
    # 输入侧中文路径按 GBK 解码成乱码导致"脚本不存在"。与 tools/run_tests.py 同款保护。
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        # v7.47：类型检查——json.loads 对 [1,2]/"str"/42/null/batch 数组均成功，
        # 此前 rid = req.get("id") 在 try 外，一行非对象消息即 AttributeError
        # 穿透 main() 杀死整个会话（单行输入 = 服务永久死亡）
        if not isinstance(req, dict):
            continue
        rid = req.get("id")
        if rid is None:  # 通知类消息（notifications/initialized 等）
            continue
        try:
            result = handle(req)
            reply = {"jsonrpc": "2.0", "id": rid, "result": result}
        except KeyError as exc:
            reply = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": "Method not found: %s" % exc},
            }
        except ValueError as exc:
            # v7.47：未知工具名/缺必填参数按 MCP 规范回 -32602 Invalid params
            reply = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32602, "message": "Invalid params: %s" % exc},
            }
        except Exception as exc:  # noqa: BLE001 - 兜底，避免打断会话
            reply = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32603, "message": "Internal error: %s" % exc},
            }
        out.write(json.dumps(reply, ensure_ascii=False) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
