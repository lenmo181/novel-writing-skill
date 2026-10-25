# -*- coding: utf-8 -*-
"""Provider：本插件不需要任何凭据（校验逻辑全部内置）。
v7.47：移除 skill_root 覆盖项——原凭据是死键：Provider 校验目录存在，但
helper.skill_root() 只读环境变量/内置副本，没有任何代码把 credentials
传给 helper（Dify 的 tool credentials 经 Tool.credentials 下发，不会自动
变成环境变量），用户在 UI 填了路径、看到"校验通过"，实际跑的仍是内置 _skill
（虚假控制感比没有选项更糟）。需要自定义技能目录请用环境变量
NOVEL_SKILL_ROOT / NOVEL_SKILL_SCRIPTS（helper.py v7.47 已对齐为优先读取）。
"""
from __future__ import annotations

from typing import Any

from dify_plugin import ToolProvider


class WebNovelWritingProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # 零配置：无凭据需要校验。保留方法以满足 ToolProvider 接口。
        return None
