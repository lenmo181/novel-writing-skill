#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dify 插件打包辅助：把技能包复制进插件目录的 ``_skill/``。

Dify 插件在沙箱内运行，必须自带校验脚本；本脚本与 ``packaging/pypi/build_wheel.py``
共用同一套排除规则，保证「wheel 内技能」与「Dify 插件内技能」内容一致。

用法
----
    python packaging/dify/bundle_skill.py            # 打包技能进 _skill/
    python packaging/dify/bundle_skill.py --clean    # 清掉 _skill/

随后：
    dify plugin package packaging/dify -o dist/
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

EXCLUDE_DIRS = {
    ".git", ".workbuddy", ".v2c", ".video_agent", "__pycache__", ".idea",
    ".vscode", ".playwright-cli", ".github", "dist", "out", "tests",
    "packaging", ".pytest_cache", "build_pkg", "_skill",
}
EXCLUDE_EXT = {".pyc", ".pyo", ".bak", ".tmp"}  # v7.47：原子写安全网产物不进 bundle


def copy_skill(dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    n = 0
    for root, dirs, files in os.walk(REPO):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if Path(name).suffix in EXCLUDE_EXT:
                continue
            src = Path(root) / name
            dst = dest / src.relative_to(REPO)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


def main() -> int:
    # 中文 Windows 的 cp936 无法编码自检输出中的 ✓，打包器不能因终端编码
    # 在收尾阶段失败；与其它发布入口统一 UTF-8 输出口径。
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="把技能包复制进 Dify 插件的 _skill/")
    ap.add_argument("--clean", action="store_true", help="删除 _skill/ 后退出")
    args = ap.parse_args()

    dest = HERE / "_skill"
    if args.clean:
        shutil.rmtree(dest, ignore_errors=True)
        print("已清理", dest)
        return 0

    n = copy_skill(dest)
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"已复制 {n} 个技能文件到 {dest.relative_to(REPO)}（{size/1024:.0f} KiB）")
    if not (dest / "tools" / "config.py").is_file():
        print("✗ 缺少 tools/config.py，技能包结构不对")
        return 1
    print("✓ 结构自检通过（tools/config.py 就位）")
    print("下一步：dify plugin package packaging/dify -o dist/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
