# -*- coding: utf-8 -*-
"""Dify 工具：章节硬卡校验。

Dify 插件跑在远端沙箱，拿不到用户本地路径，
故以「正文文本」为输入，落临时文件后调用技能包内 `check_chapter.py`。
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import run_validator_on_text  # noqa: E402


class CheckChapterTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        text = str(tool_parameters.get("chapter_text") or "")
        if not text.strip():
            yield self.create_text_message("错误：chapter_text 为空，无法校验。")
            return

        args: list[str] = []
        idx = tool_parameters.get("chapter_index")
        if idx not in (None, "", 0):
            args += ["--chapter-index", str(int(idx))]
        platform = str(tool_parameters.get("platform") or "").strip()
        if platform:
            args += ["--platform", platform]
        quote = str(tool_parameters.get("quote") or "").strip()
        if quote:
            args += ["--quote", quote]

        res = run_validator_on_text("check_chapter.py", text, extra_args=args)

        if "error" in res:
            yield self.create_text_message("校验未执行：" + res["error"])
            yield self.create_json_message({"ok": False, "error": res["error"]})
            return

        passed = res["exit_code"] == 0
        report = res["stdout"] or "(无输出)"
        if res["stderr"]:
            report += "\n\n[stderr]\n" + res["stderr"]

        header = "✅ 通过：无硬伤" if passed else "❌ 未通过：存在硬伤，禁止交付"
        yield self.create_text_message(f"{header}\n\n{report}")
        yield self.create_json_message({
            "ok": passed,
            "exit_code": res["exit_code"],
            "report": report,
            "platform": platform or "default",
            "chapter_index": int(idx) if idx not in (None, "", 0) else None,
        })
