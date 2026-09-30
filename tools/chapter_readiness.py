# -*- coding: utf-8 -*-
"""章节交付 Gate（v7.39）：工程 Gate + 可验证语义 Gate。"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from config import SKILL_VERSION

TOOLS = Path(__file__).resolve().parent
SEMANTIC_DIR = Path("mind") / "审校"
SEMANTIC_CHECKS = list(range(14, 31))

def run_gate(name, command, cwd):
    try:
        p = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        output = (p.stdout + "\n" + p.stderr).strip().splitlines()
        return {"name": name, "ok": p.returncode == 0, "exit_code": p.returncode, "tail": output[-6:]}
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "exit_code": 2, "tail": ["超过180秒未返回"]}
    except OSError as exc:
        return {"name": name, "ok": False, "exit_code": 2, "tail": [str(exc)]}

def resolve_chapter(root, chapter):
    candidates = sorted((root / "书稿").glob(f"第{chapter:03d}章*")) + sorted((root / "书稿").glob(f"第{chapter}章*"))
    return next((p for p in candidates if p.is_file()), None)

def semantic_path(root, chapter):
    return root / SEMANTIC_DIR / f"第{chapter:03d}章审校.json"

def semantic_gate(root, chapter):
    path = semantic_path(root, chapter)
    if not path.is_file():
        return {"name": "30项语义证据", "ok": False, "exit_code": 1,
                "tail": [f"缺少 {path.relative_to(root)}；需完成第14-30项语义审校并逐项记录证据"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": [f"审校记录无法解析：{exc}"]}
    if data.get("chapter") != chapter:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"审校记录 chapter={data.get(chr(34)+chr(34))} 与目标第{chapter}章不一致"]}
    checks = data.get("checks")
    if not isinstance(checks, dict):
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": ["checks 必须是对象，覆盖校验14-30"]}
    missing = []
    invalid = []
    failed = []
    for number in SEMANTIC_CHECKS:
        item = checks.get(str(number), checks.get(number))
        if not isinstance(item, dict):
            missing.append(str(number))
            continue
        status = item.get("status")
        if status not in {"pass", "warn", "revise", "blocked"}:
            invalid.append(str(number))
        if status in {"revise", "blocked"}:
            failed.append(number)
        if not str(item.get("evidence", "")).strip():
            invalid.append(f"{number}:evidence")
    if missing:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"缺少语义校验项：{chr(44).join(missing)}"]}
    if invalid:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"语义记录缺少合法 evidence/status：{chr(44).join(invalid[:8])}"]}
    if failed:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"存在未解决语义项：{chr(44).join(map(str, failed))}"]}
    return {"name": "30项语义证据", "ok": True, "exit_code": 0, "tail": [f"第14-30项共{len(SEMANTIC_CHECKS)}项均有 status + evidence"]}

def assess(root, chapter, full=False, with_semantic=False):
    target = resolve_chapter(root, chapter)
    if target is None:
        return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter, "ok": False, "input_error": True,
                "gates": [{"name": "章节存在", "ok": False, "exit_code": 2, "tail": [f"未找到第{chapter}章"]}]}
    commands = [
        ("单章机械校验", [sys.executable, str(TOOLS / "check_chapter.py"), str(target)]),
        ("项目健康", [sys.executable, str(TOOLS / "project_health.py"), str(root)]),
        ("连续性检查", [sys.executable, str(TOOLS / "continuity_check.py"), str(root)]),
        ("上下文可构建", [sys.executable, str(TOOLS / "context_pack.py"), str(root), "--chapter", str(chapter), "--format", "json"]),
    ]
    gates = [run_gate(n, c, root) for n, c in commands]
    if with_semantic:
        gates.append(semantic_gate(root, chapter))
    if full:
        gates.append(run_gate("全文审稿", [sys.executable, str(TOOLS / "full_review.py"), str(root), "--strict", "--json"], root))
    return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter,
            "target": str(target.relative_to(root)), "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "gates": gates, "ok": all(g["ok"] for g in gates), "input_error": False}

def main(argv=None):
    ap = argparse.ArgumentParser(description=f"章节交付 Gate v{SKILL_VERSION}")
    ap.add_argument("project"); ap.add_argument("chapter", type=int)
    ap.add_argument("--full", action="store_true", help="额外运行全文审稿 strict")
    ap.add_argument("--with-semantic", action="store_true", help="要求 mind/审校/第XXX章审校.json 覆盖第14-30项并逐项给证据")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir() or args.chapter < 1:
        print("[✗] 项目目录或章节号非法"); return 2
    report = assess(root, args.chapter, args.full, args.with_semantic)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser(); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(output + "\n", encoding="utf-8"); print(f"交付 Gate 已写入：{target}")
    else:
        print(output)
    return 2 if report.get("input_error") else (0 if report["ok"] else 1)

def render(report):
    lines = [f"# 章节交付 Gate（v{report[chr(39)+chr(118)+chr(101)+chr(114)+chr(115)+chr(105)+chr(111)+chr(110)]}）", "",
             f"- 第 {report[chr(39)+chr(99)+chr(104)+chr(97)+chr(112)+chr(116)+chr(101)+chr(114)]} 章：`{report.get(chr(39)+chr(116)+chr(97)+chr(114)+chr(103)+chr(101)+chr(116), chr(39)-chr(39))}`",
             "- 时间：" + report.get("generated_at", ""), "", "| Gate | 结果 | 退出码 |", "|---|---|---:|"]
    for gate in report["gates"]:
        lines.append(f"| {gate[chr(39)+chr(110)+chr(97)+chr(109)+chr(101)]} | {chr(39)+chr(80)+chr(65)+chr(83)+chr(83) if gate[chr(39)+chr(111)+chr(107)] else chr(39)+chr(82)+chr(69)+chr(86)+chr(73)+chr(83)+chr(69)} | {gate[chr(39)+chr(101)+chr(120)+chr(105)+chr(116)+chr(95)+chr(99)+chr(111)+chr(100)+chr(101)]} |")
    lines += ["", "结论：" + ("PASS，可进入交付/作者验收。" if report["ok"] else "REVISE，先处理失败 Gate。"), "",
              "语义 Gate 需要第14-30项逐项 evidence；本工具只验证记录完整性，不代替作者/AI做文学判断。",
              "失败 Gate 的详细输出已保留在 JSON 报告中；本工具不修改正文。"]
    return "\n".join(lines)

if __name__ == "__main__":
    raise SystemExit(main())
