# -*- coding: utf-8 -*-
"""技能包统一自检（v7.43）。

用途：在安装后或出现“技能找不到/闪退/脚本报错/文档不一致”时，
用一次命令检查包结构、版本真源、Python 语法和技能包内相对引用。
只读，不访问 SkillHub，不读取小说项目，也不修改技能文件。
退出码：0=通过，1=发现问题，2=输入错误。
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import sys
import subprocess
import tempfile
import zipfile
from pathlib import Path

import check_refs
from config import RELEASE_DATE, SKILL_VERSION


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DIRS = ("references", "templates", "tools", "versions", "schemas")
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "LICENSE",
    "NOTICE",
    "CONTRIBUTING.md",
    "templates/项目模板.md",
    "SECURITY.md",
    "schemas/full_review_queue.schema.json",
    "schemas/project_metadata.schema.json",
    "schemas/chapter_readiness.schema.json",
    "schemas/chapter_semantic_review.schema.json",
    "references/快速开始.md",
    "references/工具选择.md",
    "references/研究来源.md",
    "references/常见问题.md",
    "references/操作范例.md",
    "references/模式操作卡.md",
    "references/工程化能力矩阵.md",
    "references/评测场景.md",
    "references/评测量表.md",
    "tools/config.py",
    "tools/lint_skill.py",
    "tools/check_refs.py",
    "tools/sync_skill.ps1",
    "tools/update_skill.py",
    "tools/release_check.py",
    "tools/init_project.py",
    "tools/entity_index.py",
    "tools/project_health.py",
    "tools/full_review.py",
    "tools/chapter_readiness.py",
    "tools/repair_orchestrator.py",
    "tools/audit_log.py",
    "tools/memory_search.py",
)

RUNTIME_TOOLS = (
    "canonical_parser.py",
    "check_chapter.py",
    "retention_check.py",
    "script_check.py",
    "fix_said_tags.py",
    "visualize.py",
    "project_audit.py",
    "continuity_check.py",
    "context_pack.py",
    "chapter_diff.py",
    "snapshot_project.py",
    "conflict_score.py",
    "grep_consistency.py",
    "check_refs.py",
    "lint_skill.py",
    "update_skill.py",
    "cover_check.py",
    "zhuque_check.py",
    "mochi_check.py",
    "mochi_setup.py",
    "gen_index.py",
    "doctor.py",
    "eval_skill.py",
    "release_check.py",
    "init_project.py",
    "entity_index.py",
    "project_health.py",
    "full_review.py",
    "chapter_readiness.py",
    "repair_orchestrator.py",
    "audit_log.py",
    "memory_search.py",
    "repair_runner.py",
)


def runtime_smoke(root: Path, timeout: float = 8.0) -> list[dict]:
    """启动所有核心工具的 --help，验证入口可加载且不裸崩。"""
    results = []
    tools_dir = root / "tools"
    for name in RUNTIME_TOOLS:
        path = tools_dir / name
        if not path.is_file():
            results.append({"tool": name, "ok": False, "detail": "文件不存在"})
            continue
        try:
            completed = subprocess.run(
                [sys.executable, str(path), "--help"],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            ok = completed.returncode == 0
            detail = "--help 通过" if ok else f"退出码 {completed.returncode}"
        except subprocess.TimeoutExpired:
            ok, detail = False, f"超过 {timeout:g}s 未返回"
        except OSError as exc:
            ok, detail = False, str(exc)
        results.append({"tool": name, "ok": ok, "detail": detail})
    return results


def package_smoke(root: Path, timeout: float = 15.0) -> dict:
    """在临时目录完成一次 ZIP 打包、解压和安装副本自检。"""
    excluded = {".git", ".workbuddy", ".playwright-cli", ".v2c", ".video_agent", "dist", "out", "__pycache__"}
    with tempfile.TemporaryDirectory(prefix="novel_skill_package_") as temp:
        temp_root = Path(temp)
        archive = temp_root / "skill.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if not path.is_file() or any(part in excluded for part in path.relative_to(root).parts):
                    continue
                zf.write(path, path.relative_to(root).as_posix())
        extracted = temp_root / "extracted"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        doctor_path = extracted / "tools" / "doctor.py"
        if not doctor_path.is_file():
            return {"ok": False, "detail": "ZIP 解压后缺少 tools/doctor.py"}
        try:
            completed = subprocess.run(
                [sys.executable, str(doctor_path), "--json"],
                cwd=str(extracted),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            if completed.returncode != 0:
                return {"ok": False, "detail": f"解压副本自检退出码 {completed.returncode}"}
            report = json.loads(completed.stdout)
            return {"ok": bool(report.get("ok")), "detail": "ZIP 解压副本自检通过"}
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "detail": f"解压副本自检异常：{exc}"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "detail": f"解压副本自检超过 {timeout:g}s 未返回"}


def _check(label: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"label": label, "ok": bool(ok), "detail": detail, "fix": fix}


# 目录树登记完整性（v7.40）：仓库基础设施与运行产物不要求登记
# 豁免范围与上架包一致（build_market_zip.py）：tests/ 与仓库基础设施文件不随技能包分发
TREE_EXCLUDED_PARTS = {".git", ".github", ".workbuddy", ".v2c", ".video_agent",
                       ".playwright-cli", "dist", "out", "__pycache__", "tests"}
TREE_EXCLUDED_FILES = {"LICENSE", "NOTICE", "CONTRIBUTING.md", "SECURITY.md", "_meta.json", "交流群二维码.png"}
TREE_TREE_LINE_RE = re.compile(r"^[│\s]*[├└]──\s*(.+)$")


def parse_skill_tree(skill_text: str) -> tuple[set, set]:
    """解析 SKILL.md「技能目录结构」树，返回 (登记文件相对路径集合, 免登记目录集合)。

    以 `/` 结尾且未列任何子项的目录（如 versions/ 存档）视为免登记目录；
    列了子项的目录（tools/ references/ …）其子项必须逐个登记。
    """
    registered: set = set()
    dir_entries: list = []
    current_dir = ""
    in_section = False
    in_block = False
    for line in skill_text.splitlines():
        stripped = line.strip()
        if not in_section:
            if "技能目录结构" in line:
                in_section = True
            continue
        if stripped.startswith("```"):
            if not in_block:
                in_block = True
                continue
            break  # 收尾围栏：树结束
        if not in_block:
            continue
        m = TREE_TREE_LINE_RE.match(line)
        if not m:
            continue
        entry = m.group(1).split("#", 1)[0].strip().rstrip()
        if not entry:
            continue
        if entry.endswith("/"):
            current_dir = entry
            dir_entries.append(entry)
            continue
        if "/" in entry:  # 顶层内联路径（如 templates/项目模板.md）
            registered.add(entry)
        else:
            registered.add(f"{current_dir}{entry}")
    exempt = {d for d in dir_entries if not any(r.startswith(d) for r in registered)}
    return registered, exempt


def tree_registry_report(root: Path, skill_text: str) -> dict:
    """比对目录树登记与磁盘实际文件：防「手册已写、认知树里没有」的自指盲区。"""
    registered, exempt = parse_skill_tree(skill_text)
    on_disk: set = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if not path.is_file():
            continue
        parts = rel.parts
        if any(p in TREE_EXCLUDED_PARTS or p.startswith(".") for p in parts[:-1]) or parts[-1].startswith("."):
            continue
        if rel.as_posix() in TREE_EXCLUDED_FILES:
            continue
        if any(rel.as_posix().startswith(d) for d in exempt):
            continue
        on_disk.add(rel.as_posix())
    unregistered = sorted(on_disk - registered)
    phantom = sorted(registered - on_disk)
    ok = not unregistered and not phantom
    bits = []
    if unregistered:
        shown = "、".join(unregistered[:6]) + (" 等" if len(unregistered) > 6 else "")
        bits.append(f"未登记 {len(unregistered)} 个文件（{shown}）")
    if phantom:
        bits.append(f"登记但不存在 {len(phantom)} 个（{'、'.join(phantom[:4])}）")
    detail = f"登记 {len(registered & on_disk)}/{len(on_disk)}，全部一致" if ok else "；".join(bits)
    return _check(
        "目录树登记完整性",
        ok,
        detail,
        "在 SKILL.md「技能目录结构」补齐缺失文件，或把存档类目录改为「目录/ + 注释」式免登记条目" if not ok else "",
    )


def audit(root: Path = ROOT) -> dict:
    """返回可供人读或机器消费的自检报告。"""
    root = Path(root).expanduser().resolve()
    checks = []

    if not root.is_dir():
        return {
            "version": SKILL_VERSION,
            "root": str(root),
            "ok": False,
            "input_error": True,
            "checks": [_check("技能根目录", False, "目录不存在或不是目录", "确认技能目录路径")],
        }

    missing_dirs = [name for name in REQUIRED_DIRS if not (root / name).is_dir()]
    checks.append(_check(
        "目录骨架",
        not missing_dirs,
        "目录齐全" if not missing_dirs else f"缺少：{', '.join(missing_dirs)}",
        "恢复缺失目录或重新同步技能包" if missing_dirs else "",
    ))

    missing_files = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    checks.append(_check(
        "必需文件",
        not missing_files,
        "必需文件齐全" if not missing_files else f"缺少：{', '.join(missing_files)}",
        "重新运行 tools/sync_skill.ps1" if missing_files else "",
    ))

    skill_text = ""
    readme_text = ""
    try:
        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        checks.append(_check("文档可读性", False, str(exc), "确认文件编码为 UTF-8 且目录可读"))
    else:
        version_ok = f"v{SKILL_VERSION}" in skill_text and f"v{SKILL_VERSION}" in readme_text
        date_ok = RELEASE_DATE in skill_text and RELEASE_DATE in readme_text
        checks.append(_check(
            "版本真源",
            version_ok and date_ok,
            f"v{SKILL_VERSION} / {RELEASE_DATE}" if version_ok and date_ok else "主规则、README 与 config.py 不一致",
            "先运行 tools/lint_skill.py，按报告修复版本或日期漂移" if not (version_ok and date_ok) else "",
        ))

    syntax_errors = []
    tools_dir = root / "tools"
    if tools_dir.is_dir():
        for path in sorted(tools_dir.glob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                syntax_errors.append(f"{path.name}: {exc}")
    checks.append(_check(
        "工具语法",
        not syntax_errors,
        "tools/*.py 语法通过" if not syntax_errors else "；".join(syntax_errors),
        "先修复语法错误，再运行回归测试" if syntax_errors else "",
    ))

    ref_output = io.StringIO()
    try:
        with contextlib.redirect_stdout(ref_output):
            ref_code = check_refs.check(str(root))
        refs_ok = ref_code == 0
        ref_detail = "技能包内引用完整" if refs_ok else "存在悬空引用"
    except Exception as exc:  # pragma: no cover - 仅用于故障兜底
        refs_ok = False
        ref_detail = f"引用检查异常：{exc}"
    checks.append(_check(
        "相对引用",
        refs_ok,
        ref_detail,
        "运行 python tools/check_refs.py 查看具体悬空路径" if not refs_ok else "",
    ))

    if skill_text:
        checks.append(tree_registry_report(root, skill_text))

    return {
        "version": SKILL_VERSION,
        "release_date": RELEASE_DATE,
        "root": str(root),
        "ok": all(item["ok"] for item in checks),
        "input_error": False,
        "checks": checks,
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="网络小说创作技能统一自检：结构、版本、语法与相对引用"
    )
    parser.add_argument("root", nargs="?", default=str(ROOT), help="技能包根目录")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--runtime-smoke", action="store_true", help="启动核心工具 --help 做运行级冒烟测试")
    parser.add_argument("--package-smoke", action="store_true", help="临时打包、解压并自检安装副本")
    args = parser.parse_args(argv)
    report = audit(Path(args.root))

    if not report.get("input_error"):
        if args.runtime_smoke:
            smoke = runtime_smoke(Path(args.root).expanduser().resolve())
            passed = all(item["ok"] for item in smoke)
            report["checks"].append(_check(
                "运行级冒烟",
                passed,
                f"{sum(item['ok'] for item in smoke)}/{len(smoke)} 个工具入口通过" if passed else "存在工具入口未通过",
                "逐项运行失败工具的 --help 并修复依赖或参数入口" if not passed else "",
            ))
        if args.package_smoke:
            packed = package_smoke(Path(args.root).expanduser().resolve())
            report["checks"].append(_check(
                "打包安装冒烟",
                packed["ok"],
                packed["detail"],
                "检查 ZIP 内容、相对路径和解压副本的 tools/config.py" if not packed["ok"] else "",
            ))
        report["ok"] = all(item["ok"] for item in report["checks"])

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"网络小说创作技能 v{report['version']} 统一自检")
        print(f"根目录：{report['root']}")
        for item in report["checks"]:
            mark = "✓" if item["ok"] else "✗"
            print(f"[{mark}] {item['label']}：{item['detail']}")
            if not item["ok"] and item["fix"]:
                print(f"    建议：{item['fix']}")
        print("结论：通过" if report["ok"] else "结论：需要修复")
        if report["ok"]:
            print("下一步：普通写作直接说“初始化项目”或“写第1章”；需要选工具时查看 references/工具选择.md")
    if report.get("input_error"):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
