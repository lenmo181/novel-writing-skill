# -*- coding: utf-8 -*-
"""发布前只读预检（v7.30）。

运行技能自检、评测矩阵、lint、引用检查和可选回归测试；
可额外比对本地安装副本。不会上传 SkillHub，也不会替换任何文件。
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
COMPARE_FILES = (
    "SKILL.md",
    "README.md",
    "tools/config.py",
    "tools/doctor.py",
    "tools/eval_skill.py",
    "references/模式操作卡.md",
    "references/评测场景.md",
    "references/评测量表.md",
    "references/回执协议.md",
)


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
    for rel in COMPARE_FILES:
        source = root / rel
        target = installed / rel
        if not source.is_file():
            source_missing.append(rel)  # 源侧缺失：发布前必须暴露（此前静默判一致）
        elif not target.is_file():
            missing.append(rel)
        elif sha256(source) != sha256(target):
            different.append(rel)
    ok = not missing and not different and not source_missing
    parts = []
    if source_missing:
        parts.append(f"工作区缺失 {len(source_missing)} 个比对文件")
    if missing:
        parts.append(f"安装副本缺失 {len(missing)} 个文件")
    if different:
        parts.append(f"{len(different)} 个文件内容不同")
    detail = "本地安装副本与工作区一致" if ok else "；".join(parts)
    return {"name": "安装副本比对", "ok": ok, "exit_code": 0 if ok else 1,
            "detail": detail, "missing": missing, "different": different,
            "source_missing": source_missing}


def audit(root: Path = ROOT, installed: Optional[Path] = None, include_tests: bool = False) -> dict:
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
    return {"version": SKILL_VERSION, "root": str(root), "ok": all(item["ok"] for item in checks),
            "input_error": False, "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="网络小说创作技能发布前只读预检")
    parser.add_argument("root", nargs="?", default=str(ROOT), help="技能包根目录")
    parser.add_argument("--installed", default="", help="本地安装副本路径，只做内容比对")
    parser.add_argument("--tests", action="store_true", help="额外运行完整回归测试")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    report = audit(Path(args.root), Path(args.installed) if args.installed else None, args.tests)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"网络小说创作技能 v{report['version']} 发布前预检")
        for item in report["checks"]:
            mark = "✓" if item["ok"] else "✗"
            print(f"[{mark}] {item['name']}")
            for line in item.get("tail", []):
                print(f"    {line}")
            if item.get("detail"):
                print(f"    {item['detail']}")
        print("结论：预检通过（未上传 SkillHub）" if report["ok"] else "结论：需要修复")
    if report.get("input_error"):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
