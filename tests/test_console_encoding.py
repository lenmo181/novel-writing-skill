# -*- coding: utf-8 -*-
"""Windows GBK 控制台回归：所有 CLI 入口必须以 UTF-8 输出。

Python 3.14 在 Windows 默认把 stdout/stderr 绑到 GBK；工具打印 [✓]、→、
书名等非 GBK 字符时会直接写坏字节。父进程用 subprocess(text=True,
encoding=utf-8) 消费时，后台 reader 线程抛 UnicodeDecodeError，测试串里会
出现“成功但带异常线程”的噪声，严重时不返回预期文本。这里静态钉住登记表，
并用 PYTHONIOENCODING=gbk 跑一个会打印 [✓] 的最小真实入口。
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import doctor  # noqa: E402


class TestConsoleEncoding(unittest.TestCase):
    def _cli_scripts(self):
        for name in doctor.RUNTIME_TOOLS:
            path = TOOLS / name
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(path))
            except (OSError, UnicodeError, SyntaxError):
                continue
            has_main = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "main"
                for node in ast.walk(tree)
            )
            if has_main:
                yield name, text

    def test_runtime_cli_outputs_are_utf8(self):
        required_stdout = 'sys.stdout.reconfigure(encoding="utf-8", errors="replace")'
        required_stderr = 'sys.stderr.reconfigure(encoding="utf-8", errors="replace")'
        missing = [
            name for name, text in self._cli_scripts()
            if required_stdout not in text or required_stderr not in text
        ]
        self.assertFalse(
            missing,
            f"以下 CLI 工具未同时配置 stdout/stderr UTF-8：{missing}；"
            "新增 CLI 工具必须在 main() 或模块入口配置 sys.stdout.reconfigure 和 sys.stderr.reconfigure",
        )

    def test_repair_runner_output_survives_gbk_child_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "mind" / "全文审稿队列.json"
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text(json.dumps({
                "version": "7.45",
                "round": 1,
                "issues": [{
                    "issue_id": "FR-01-001",
                    "level": "P1",
                    "cat": "单章",
                    "loc": "第1章",
                    "msg": "测试问题",
                    "evidence": "测试",
                    "recommended_action": "人工修复",
                    "repair_scope": "病灶段",
                    "forbidden_action": "整章重写",
                    "status": "open",
                }],
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            env = {**os.environ, "PYTHONIOENCODING": "gbk"}
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "repair_runner.py"), str(root),
                 "--mark-fixed", "FR-01-001"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("[✓]", proc.stdout)
            self.assertIn("→", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
