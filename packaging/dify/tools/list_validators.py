# -*- coding: utf-8 -*-
"""Dify 工具：列出插件内置的只读校验器。"""
from __future__ import annotations

import os
import sys
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import READONLY_TOOLS, scripts_dir, skill_root  # noqa: E402


class ListValidatorsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        sd = scripts_dir()
        # v7.47：验证磁盘存在性再列出——此前直接打印 READONLY_TOOLS 全集，
        # bundle 不完整（漏文件）时会宣传不存在的校验器，用户调用了才报错；
        # 与 MCP discover_tools（白名单 ∩ 磁盘实存）口径对齐
        available = [t for t in READONLY_TOOLS if (sd / t).is_file()]
        missing = [t for t in READONLY_TOOLS if t not in available]
        lines = [
            f"技能根目录：{skill_root()}",
            f"脚本目录：{sd}",
            f"可用只读校验器（{len(available)}）：",
        ]
        lines += [f"  - {t}" for t in available]
        if missing:
            lines.append("")
            lines.append(f"⚠️ 白名单中 {len(missing)} 个脚本缺失（bundle 不完整？）：{', '.join(missing)}")
        if not sd.is_dir():
            lines.append("")
            lines.append("⚠️ 脚本目录不存在：插件未打包技能。运行 packaging/dify/bundle_skill.py 后重新打包。")
        body = "\n".join(lines)
        yield self.create_text_message(body)
        yield self.create_json_message({
            "skill_root": str(skill_root()),
            "scripts_dir": str(sd),
            "scripts_dir_exists": sd.is_dir(),
            "validators": available,
            "missing_validators": missing,
        })
