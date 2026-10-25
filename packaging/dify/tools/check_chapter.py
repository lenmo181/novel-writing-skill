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
        chapter_no: int | None = None
        if idx not in (None, "", 0):
            # v7.47：int(idx) 未捕获——LLM/工作流传入非数字串（"第一章"）时
            # ValueError 穿透 _invoke 变成 Dify 无信息量 500；0.5 类小数被
            # int() 静默截断为 0（章号 0 无意义且关闭开篇闸门推断）
            try:
                chapter_no = int(idx)
            except (TypeError, ValueError):
                yield self.create_text_message(f"错误：chapter_index 必须是数字，收到 {idx!r}")
                yield self.create_json_message({"ok": False, "error": "chapter_index 必须是数字"})
                return
            if chapter_no < 1:
                yield self.create_text_message(f"错误：chapter_index 必须 ≥1，收到 {chapter_no}")
                yield self.create_json_message({"ok": False, "error": "chapter_index 必须 ≥1"})
                return
            args += ["--chapter-index", str(chapter_no)]
        platform = str(tool_parameters.get("platform") or "").strip()
        # v7.47：platform/quote 前置白名单校验——此前原样透传，非法值以 argparse
        # 错误（退出码 2 + 用法到 stderr）形式呈现；YAML zhihu 选项即因此必失败
        import config as _skill_config
        if platform and platform not in _skill_config.PLATFORM_PRESETS:
            yield self.create_text_message(
                f"错误：platform 非法（{platform}），可选：{sorted(_skill_config.PLATFORM_PRESETS)}")
            yield self.create_json_message({"ok": False, "error": "platform 非法"})
            return
        if platform:
            args += ["--platform", platform]
        quote = str(tool_parameters.get("quote") or "").strip()
        if quote and quote not in _skill_config.QUOTE_MODES:
            yield self.create_text_message(
                f"错误：quote 非法（{quote}），可选：{sorted(_skill_config.QUOTE_MODES)}")
            yield self.create_json_message({"ok": False, "error": "quote 非法"})
            return
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
            "chapter_index": chapter_no,
        })
