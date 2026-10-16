#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络小说创作技能 · PyPI wheel 构建器（纯标准库，零第三方依赖）

为什么不用 `python -m build` / setuptools
----------------------------------------
本技能全链路的工程约束是「纯 Python 标准库、零第三方依赖」，构建链也不例外。
本脚本用 ``zipfile`` + ``hashlib`` 直接产出一个符合 PEP 427 的 wheel，
并用 ``pip install`` 本地自证可安装。若环境已有 ``build``/``setuptools``，
也可直接进 ``packaging/pypi/build_pkg/`` 跑标准构建（脚本会同时生成
标准 ``pyproject.toml``）。

产物
----
- 源树：``packaging/pypi/build_pkg/``（可 gitignore）
- wheel：``dist/web_novel_writing_mcp-<ver>-py3-none-any.whl``

包内布局
--------
```
web_novel_writing_mcp/
  __init__.py
  server.py            # MCP Server（JSON-RPC over stdio）
  _skill/              # 完整技能包（SKILL.md / tools / references / versions ...）
    tools/             # config.py 的 parents[1] == _skill/，故 doctor.py 可全绿
```
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent                 # packaging/pypi
PKG_ROOT = HERE.parent                                  # packaging
REPO = PKG_ROOT.parent                                  # 仓库根

PKG_NAME = "web-novel-writing-mcp"
MODULE = "web_novel_writing_mcp"
CONSOLE = "web-novel-writing-mcp"
AUTHOR = "豫晨"
AUTHOR_EMAIL = "lenmo181@users.noreply.github.com"
HOMEPAGE = "https://github.com/lenmo181/novel-writing-skill"
LICENSE = "Apache-2.0"

BUILD_DIR = HERE / "build_pkg"
DIST_DIR = REPO / "dist"

EXCLUDE_DIRS = {
    ".git", ".workbuddy", ".v2c", ".video_agent", "__pycache__", ".idea",
    ".vscode", ".playwright-cli", ".github", "dist", "out", "tests",
    "packaging", ".pytest_cache", "build_pkg",
}
EXCLUDE_SUFFIX = {".pyc", ".pyo"}


# --------------------------------------------------------------------------- #
def read_version() -> str:
    """从 SKILL.md frontmatter 读版本（唯一真源）。"""
    text = (REPO / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*([0-9][0-9A-Za-z.\-]*)", text, re.M)
    if not m:
        raise SystemExit("SKILL.md 未找到 version 字段")
    return m.group(1).strip()


def clean_build_dir() -> None:
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)


def copy_skill(dest: Path) -> list[Path]:
    """把完整技能包复制到 ``dest``，返回落盘文件列表（相对 dest）。"""
    written: list[Path] = []
    dest.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(REPO):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if Path(name).suffix in EXCLUDE_SUFFIX:
                continue
            src = Path(root) / name
            rel = src.relative_to(REPO)
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(rel)
    return written


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# wheel 组装（PEP 427 / PEP 376）
# --------------------------------------------------------------------------- #
def hash_record(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# 仅用于「标准构建」的脚手架文件，不进 wheel 载荷本身
SKIP_IN_WHEEL = {"pyproject.toml", "README.md"}


def emit_pyproject(version: str) -> None:
    """生成标准 PEP 621 项目文件，便于 `python -m build` / `pip install .`。

    本脚本自身的 stdlib 构建器不使用它；它服务于「环境里已有 setuptools」的使用者。
    """
    write_text(BUILD_DIR / "pyproject.toml", f"""[build-system]
requires = ["setuptools>=62", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{PKG_NAME}"
version = "{version}"
description = "MCP server and validator toolkit for long-form Chinese web novel authoring"
readme = "README.md"
requires-python = ">=3.9"
license = {{ text = "{LICENSE}" }}
authors = [{{ name = "{AUTHOR}", email = "{AUTHOR_EMAIL}" }}]
keywords = ["mcp", "agent-skills", "novel", "writing", "chinese", "web-novel"]
classifiers = [
  "Development Status :: 5 - Production/Stable",
  "Environment :: Console",
  "License :: OSI Approved :: Apache Software License",
  "Natural Language :: Chinese (Simplified)",
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Topic :: Text Processing",
]
dependencies = []

[project.urls]
Homepage = "{HOMEPAGE}"
Repository = "{HOMEPAGE}"
SkillHub = "https://skillhub.cn/skills/user_cd8383ec/web-novel-writing"
ModelScope = "https://www.modelscope.cn/skills/lenmo181/web-novel-writing"

[project.scripts]
{CONSOLE} = "{MODULE}.server:main"

[tool.setuptools]
packages = ["{MODULE}"]

[tool.setuptools.package-data]
"{MODULE}" = ["_skill/**/*", "*.py"]
""")
    if (REPO / "README.en.md").is_file():
        shutil.copy2(REPO / "README.en.md", BUILD_DIR / "README.md")


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if Path(f).suffix in EXCLUDE_SUFFIX:
                continue
            out.append(Path(r) / f)
    return sorted(out)


def build_wheel(version: str) -> Path:
    clean_build_dir()

    # 1) 包目录
    pkg_dir = BUILD_DIR / MODULE
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 1a) 完整技能包 -> _skill/
    n_skill = len(copy_skill(pkg_dir / "_skill"))

    # 1b) MCP Server 源（唯一真源 = packaging/mcp/server.py）
    shutil.copy2(PKG_ROOT / "mcp" / "server.py", pkg_dir / "server.py")

    write_text(pkg_dir / "__init__.py", (
        '"""网络小说创作技能 · MCP Server（PyPI 分发形态）。\n\n'
        f'版本：{version}\n'
        '完整技能包随包分发在 ``web_novel_writing_mcp/_skill/``，\n'
        '服务器脚本见 ``web_novel_writing_mcp/server.py``。\n'
        '"""\n\n'
        f'__version__ = "{version}"\n'
        '__all__ = ["__version__"]\n'
    ))
    write_text(pkg_dir / "__main__.py", (
        "from .server import main\n\nif __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    ))

    # 2) dist-info
    dist_info = BUILD_DIR / f"{MODULE}-{version}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)

    readme = (REPO / "README.en.md")
    long_desc = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {PKG_NAME}\n"
        f"Version: {version}\n"
        "Summary: MCP server and validator toolkit for long-form Chinese web "
        "novel authoring (network fiction)\n"
        f"Author: {AUTHOR}\n"
        f"Author-email: {AUTHOR_EMAIL}\n"
        f"License: {LICENSE}\n"
        f"Home-page: {HOMEPAGE}\n"
        "Project-URL: Repository, "
        "https://github.com/lenmo181/novel-writing-skill\n"
        "Project-URL: SkillHub, "
        "https://skillhub.cn/skills/user_cd8383ec/web-novel-writing\n"
        "Project-URL: ModelScope, "
        "https://www.modelscope.cn/skills/lenmo181/web-novel-writing\n"
        "Keywords: mcp,agent-skills,novel,writing,chinese,web-novel,"
        "creative-writing,prompt-engineering\n"
        "Classifier: Development Status :: 5 - Production/Stable\n"
        "Classifier: Environment :: Console\n"
        "Classifier: Intended Audience :: End Users/Desktop\n"
        "Classifier: License :: OSI Approved :: Apache Software License\n"
        "Classifier: Natural Language :: Chinese (Simplified)\n"
        "Classifier: Operating System :: OS Independent\n"
        "Classifier: Programming Language :: Python :: 3\n"
        "Classifier: Topic :: Text Processing\n"
        "Requires-Python: >=3.9\n"
        "Description-Content-Type: text/markdown\n"
        "\n" + long_desc
    )
    write_text(dist_info / "METADATA", metadata)

    write_text(dist_info / "WHEEL", (
        "Wheel-Version: 1.0\n"
        "Generator: novel-skill-wheelbuilder (stdlib)\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ))
    write_text(dist_info / "entry_points.txt", (
        "[console_scripts]\n"
        f"{CONSOLE} = {MODULE}.server:main\n"
    ))
    write_text(dist_info / "top_level.txt", MODULE + "\n")

    # 2b) 标准构建脚手架（不随 wheel 载荷分发）
    emit_pyproject(version)

    # 3) 收集并写 zip
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    wheel_path = DIST_DIR / f"{MODULE}-{version}-py3-none-any.whl"

    records: list[tuple[str, str, int]] = []
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in iter_files(BUILD_DIR):
            arc = f.relative_to(BUILD_DIR).as_posix()
            if arc in SKIP_IN_WHEEL:
                continue
            data = f.read_bytes()
            zf.writestr(arc, data)
            records.append((arc, hash_record(data), len(data)))
        # RECORD 自身：hash/size 留空
        record_arc = f"{MODULE}-{version}.dist-info/RECORD"
        lines = ["%s,%s,%d" % r for r in records]
        lines.append(f"{record_arc},,")
        zf.writestr(record_arc, "\n".join(lines) + "\n")

    return wheel_path, n_skill


# --------------------------------------------------------------------------- #
def self_check(wheel: Path) -> bool:
    """把 wheel 装进临时目录并跑 MCP 握手，自证可安装可运行。"""
    tmp = REPO / ".workbuddy" / "tmp" / "wheel_check"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
         "--target", str(tmp), str(wheel)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        return False

    server = tmp / MODULE / "server.py"
    if not server.is_file():
        print("  ✗ 安装后未找到 server.py")
        return False
    if not (tmp / MODULE / "_skill" / "tools" / "config.py").is_file():
        print("  ✗ 安装后未找到 _skill/tools/config.py")
        return False

    msgs = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"2025-06-18","capabilities":{},'
        '"clientInfo":{"name":"selfcheck","version":"1"}}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":'
        '{"name":"doctor","arguments":{}}}\n'
    )
    run = subprocess.run(
        [sys.executable, str(server)],
        input=msgs, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    lines = [l for l in (run.stdout or "").splitlines() if l.strip()]
    if len(lines) < 2:
        print("  ✗ MCP 无响应：", run.stdout, run.stderr)
        return False
    import json as _json
    init = _json.loads(lines[0])["result"]["serverInfo"]
    body = _json.loads(lines[1])["result"]["content"][0]["text"]
    ok = "93/93" in body or "全部一致" in body
    print(f"  ✓ 握手 OK：{init['name']} v{init['version']}")
    print(f"  ✓ doctor 输出：{'全绿' if ok else '见下'}")
    if not ok:
        print("    " + body.replace("\n", "\n    ")[:800])
    shutil.rmtree(tmp, ignore_errors=True)
    return ok


def main() -> int:
    version = read_version()
    print(f"构建 {PKG_NAME} v{version}")
    wheel, n_skill = build_wheel(version)
    size = wheel.stat().st_size
    print(f"  ✓ 打包技能文件 {n_skill} 个")
    print(f"  ✓ wheel：{wheel.relative_to(REPO)}  ({size/1024:.0f} KiB)")
    print("自检（安装到临时目录 + MCP 握手 + 跑 doctor）…")
    ok = self_check(wheel)
    print("结论：" + ("通过 ✅" if ok else "失败 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
