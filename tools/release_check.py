# -*- coding: utf-8 -*-
"""发布前只读预检（v7.46）。

运行技能自检、评测矩阵、lint、引用检查和可选回归测试；
可额外比对本地安装副本。不会上传 SkillHub，也不会替换任何文件。

v7.43 新增两道发布链门禁：
  1. 版本 tag：HEAD 是否落在 v* tag 上——决定该版本的 dist 包日后能否从源码重建
     （v7.35-38 的包就是因为从未打 tag 而无法重建）。默认警告，`--strict` 下判失败。
  2. 发布包同号：dist/ 是否存在与当前版本同号的 zip——防「代码已升版、包还是上一版」。
退出码：0=预检通过，1=发现问题，2=输入错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import SKILL_VERSION


ROOT = Path(__file__).resolve().parents[1]
COMPARE_FILES = ("references/评测场景.md", "references/评测量表.md", "references/工具选择.md")  # legacy compatibility alias
RUNTIME_DIRS = ("tools", "references", "schemas", "templates")
RUNTIME_ROOT_FILES = ("SKILL.md", "README.md", "LICENSE", "NOTICE", "CONTRIBUTING.md", "SECURITY.md")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_check(name: str, command: list[str], root: Path) -> dict:
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        output = (completed.stdout + completed.stderr).strip().splitlines()
        return {
            "name": name,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "tail": output[-4:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "ok": False, "exit_code": 2, "tail": [str(exc)]}


def compare_installed(root: Path, installed: Path) -> dict:
    missing = []
    source_missing = []
    different = []
    rels = []
    for rel_root in RUNTIME_DIRS:
        base = root / rel_root
        if base.is_dir():
            rels.extend(str(p.relative_to(root)).replace("\\", "/") for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    rels.extend(RUNTIME_ROOT_FILES)
    for rel in sorted(set(rels)):
        source = root / rel
        target = installed / rel
        if not source.is_file():
            source_missing.append(rel)
        elif not target.is_file():
            missing.append(rel)
        elif sha256(source) != sha256(target):
            different.append(rel)
    ok = not missing and not different and not source_missing
    parts = []
    if source_missing:
        parts.append(f"工作区缺失 {len(source_missing)} 个运行时文件")
    if missing:
        parts.append(f"安装副本缺失 {len(missing)} 个运行时文件")
    if different:
        parts.append(f"{len(different)} 个运行时文件内容不同")
    detail = "本地安装副本与工作区 runtime 一致" if ok else "；".join(parts)
    return {"name": "安装副本比对", "ok": ok, "exit_code": 0 if ok else 1,
            "detail": detail, "files_compared": len(set(rels)), "missing": missing,
            "different": different, "source_missing": source_missing}


def git_tag_check(root: Path) -> dict:
    """HEAD 是否落在 v* tag 上：决定该版本发布包日后能否从源码重建。"""
    if not (root / ".git").exists():
        return {"name": "版本 tag", "ok": True, "exit_code": 0,
                "detail": "非 git 工作区，跳过 tag 检查"}
    proc = subprocess.run(["git", "describe", "--tags", "--exact-match", "HEAD"],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode == 0 and proc.stdout.strip():
        tag = proc.stdout.strip()
        # tag 形如 v7.43.0，config 形如 7.43——去前缀 v 与补丁位 .0 后比对
        tag_ver = tag.lstrip("v")
        if tag_ver.endswith(".0"):
            tag_ver = tag_ver[:-2]
        if tag_ver != SKILL_VERSION:
            return {"name": "版本 tag", "ok": False, "exit_code": 1,
                    "detail": f"HEAD 位于 {tag}，但当前版本是 v{SKILL_VERSION}——"
                              "改版后需重新 `git tag -a v<新版本>`，否则发布包与代码对不上"}
        return {"name": "版本 tag", "ok": True, "exit_code": 0,
                "detail": f"HEAD 位于 {tag}，与当前版本一致，该版本发布包可重建"}
    return {"name": "版本 tag", "ok": False, "exit_code": 1,
            "detail": "HEAD 未打 tag——该版本 dist 包日后无法从源码重建；"
                      "先 `git tag -a v<版本> -m \"…\"` 再发布"}


def dist_package_check(root: Path, version: str) -> dict:
    """dist/ 是否存在与当前版本同号的发布包：防「代码已升版、包还是上一版」。"""
    dist = root / "dist"
    if not dist.is_dir():
        return {"name": "发布包同号", "ok": False, "exit_code": 1,
                "detail": "dist/ 不存在，尚未构建发布包"}
    hits = sorted(p.name for p in dist.glob(f"*{version}*.zip"))
    if hits:
        return {"name": "发布包同号", "ok": True, "exit_code": 0,
                "detail": f"命中：{'，'.join(hits)}"}
    existing = sorted(p.name for p in dist.glob("*.zip"))[-3:]
    return {"name": "发布包同号", "ok": False, "exit_code": 1,
            "detail": f"dist/ 没有 v{version} 的发布包（现有最新：{'，'.join(existing) or '无'}）；"
                      "先用构建脚本出包再发布"}


def audit(root: Path = ROOT, installed: Optional[Path] = None, include_tests: bool = False,
          strict: bool = False) -> dict:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return {"version": SKILL_VERSION, "root": str(root), "ok": False,
                "input_error": True, "checks": [{"name": "根目录", "ok": False, "exit_code": 2, "tail": ["目录不存在或不是目录"]}]}

    py = sys.executable
    checks = [
        run_check("统一自检", [py, str(root / "tools" / "doctor.py"), "--runtime-smoke", "--package-smoke"], root),
        run_check("评测矩阵", [py, str(root / "tools" / "eval_skill.py"), "--json"], root),
        run_check("技能 lint", [py, str(root / "tools" / "lint_skill.py")], root),
        run_check("相对引用", [py, str(root / "tools" / "check_refs.py")], root),
    ]
    if include_tests:
        checks.append(run_check("回归测试", [py, "-W", "error", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], root))
    if installed is not None:
        checks.append(compare_installed(root, Path(installed).expanduser().resolve()))

    # 发布链门禁：tag 默认警告（--strict 判失败），发布包同号始终判失败
    warnings = []
    tag = git_tag_check(root)
    if tag["ok"]:
        warnings.append({"name": tag["name"], "detail": tag["detail"]})
    elif strict:
        checks.append({"name": tag["name"], "ok": False, "exit_code": tag["exit_code"],
                       "tail": [tag["detail"]]})
    else:
        warnings.append({"name": tag["name"], "detail": tag["detail"]})
    checks.append(dist_package_check(root, SKILL_VERSION))

    return {"version": SKILL_VERSION, "root": str(root), "ok": all(item["ok"] for item in checks),
            "input_error": False, "checks": checks, "warnings": warnings, "strict": strict}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="网络小说创作技能发布前只读预检")
    parser.add_argument("root", nargs="?", default=str(ROOT), help="技能包根目录")
    parser.add_argument("--installed", default="", help="本地安装副本路径，只做内容比对")
    parser.add_argument("--tests", action="store_true", help="额外运行完整回归测试")
    parser.add_argument("--strict", action="store_true", help="把版本 tag 警告升级为失败（正式发布建议开启）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    report = audit(Path(args.root), Path(args.installed) if args.installed else None,
                   args.tests, args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"网络小说创作技能 v{report['version']} 发布前预检"
              f"{'（严格模式）' if report.get('strict') else ''}")
        for item in report["checks"]:
            mark = "✓" if item["ok"] else "✗"
            print(f"[{mark}] {item['name']}")
            for line in item.get("tail", []):
                print(f"    {line}")
            if item.get("detail"):
                print(f"    {item['detail']}")
        for item in report.get("warnings", []):
            print(f"[!] {item['name']}")
            print(f"    {item['detail']}")
        print("结论：预检通过（未上传 SkillHub）" if report["ok"] else "结论：需要修复")
    if report.get("input_error"):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
