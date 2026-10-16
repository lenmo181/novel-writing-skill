# -*- coding: utf-8 -*-
"""Provider：本插件不需要任何凭据（校验逻辑全部内置），
仅提供一个可选的 skill_root 覆盖项，供高级用户在自托管环境替换技能目录。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class WebNovelWritingProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        root = str(credentials.get("skill_root") or "").strip()
        if root and not Path(root).is_dir():
            raise ToolProviderCredentialValidationError(
                f"skill_root 不存在或不是目录：{root}"
            )
