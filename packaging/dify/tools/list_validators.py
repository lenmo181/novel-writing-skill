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
        lines = [
            f"技能根目录：{skill_root()}",
            f"脚本目录：{sd}",
            f"可用只读校验器（{len(READONLY_TOOLS)}）：",
        ]
        lines += [f"  - {t}" for t in READONLY_TOOLS]
        if not sd.is_dir():
            lines.append("")
            lines.append("⚠️ 脚本目录不存在：插件未打包技能。运行 packaging/dify/bundle_skill.py 后重新打包。")
        body = "\n".join(lines)
        yield self.create_text_message(body)
        yield self.create_json_message({
            "skill_root": str(skill_root()),
            "scripts_dir": str(sd),
            "scripts_dir_exists": sd.is_dir(),
            "validators": list(READONLY_TOOLS),
        })
