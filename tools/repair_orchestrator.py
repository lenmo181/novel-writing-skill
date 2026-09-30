# -*- coding: utf-8 -*-
"""全文修复编排器（v7.39）。

默认路径：读取诊断队列 → 生成任务包；任何正文写入都必须显式 --apply。
机械修复只允许处理任务包中明确命中的章节，不再对整个书稿横扫。
流程：prepare →（显式授权）apply-mechanical → verify。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SKILL_VERSION
import snapshot_project
import audit_log

QUEUE = Path("mind") / "全文审稿队列.json"
PLAN = Path("mind") / "全文修复任务包.json"
MECHANICAL_HINTS = ("他说：", "她说：", "说道", "文字墙", "元信息残留", "格式残留")

def queue_sha256(root):
    path = root / QUEUE
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_queue(root):
    path = root / QUEUE
    if not path.is_file():
        raise FileNotFoundError(f"不存在全文审稿队列：{path}")
    return json.loads(path.read_text(encoding="utf-8"))

def classify(issue):
    msg = issue.get("msg", "")
    return "mechanical_candidate" if any(token in msg for token in MECHANICAL_HINTS) else "ai_assisted"

def prepare(root):
    queue = load_queue(root)
    issues = queue.get("issues") or []
    plan = {
        "version": SKILL_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "round": queue.get("round"),
        "project": str(root),
        "snapshot_required": True,
        "write_authorization_required": True,
        "queue_sha256": queue_sha256(root),
        "issues": [
            {**issue, "repair_mode": classify(issue),
             "verification": ["check_chapter.py", "chapter_diff.py", "continuity_check.py", "full_review.py"]}
            for issue in issues
        ],
    }
    target = root / PLAN
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_log.append_event(root, "repair_plan_created", str(PLAN), "open", {"issue_count": len(issues)})
    return plan, target

def load_plan(root):
    path = root / PLAN
    if not path.is_file():
        raise FileNotFoundError(f"不存在修复任务包：{path}")
    return json.loads(path.read_text(encoding="utf-8"))

def resolve_targets(root):
    """只解析任务包中机械候选项明确指出的章节；无明确章节则不自动写。"""
    plan = load_plan(root)
    expected = plan.get("queue_sha256")
    if expected and expected != queue_sha256(root):
        raise ValueError("修复队列已变化：当前队列与 prepare 时不一致，拒绝直接写入；请重新 prepare")
    targets = []
    seen = set()
    for issue in plan.get("issues", []):
        if issue.get("repair_mode") != "mechanical_candidate":
            continue
        loc = str(issue.get("loc", ""))
        chapter_nums = {int(x) for x in re.findall(r"第\s*(\d{1,6})\s*章", loc)}
        for number in sorted(chapter_nums):
            matches = sorted((root / "书稿").glob(f"第{number:03d}章*"))
            matches += sorted((root / "书稿").glob(f"第{number}章*"))
            for path in matches:
                if path.is_file():
                    path = path.resolve()
                    if path not in seen:
                        seen.add(path)
                        targets.append(path)
                    break
    return targets

def run_cmd(command, root):
    try:
        p = subprocess.run(command, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        return {"ok": p.returncode == 0, "exit_code": p.returncode,
                "tail": (p.stdout + "\n" + p.stderr).strip().splitlines()[-8:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "exit_code": 2, "tail": [str(exc)]}

def apply_mechanical(root, files):
    if not files:
        return {"snapshot": None, "files": [], "repair": {"ok": True, "exit_code": 0, "tail": ["没有可安全自动修复的机械候选项，未修改正文"]}}
    snap, _ = snapshot_project.create_snapshot(root, "pre-repair-mechanical", include_chapters=True)
    command = [sys.executable, str(Path(__file__).resolve().parent / "fix_said_tags.py"), "--files", *map(str, files), "--walls", "--meta"]
    result = run_cmd(command, root)
    status = "auto_fixed" if result["ok"] else "open"
    audit_log.append_event(root, "mechanical_repair", str(root / "书稿"), status,
                           {"snapshot": str(snap), "exit_code": result["exit_code"],
                            "files": [str(p.relative_to(root)) for p in files]})
    return {"snapshot": str(snap), "files": [str(p) for p in files], "repair": result}

def verify(root, full=False):
    command = [sys.executable, str(Path(__file__).resolve().parent / "full_review.py"), str(root), "--json"]
    if full:
        command.insert(-1, "--strict")
    result = run_cmd(command, root)
    audit_log.append_event(root, "repair_verification", str(QUEUE), "verified" if result["ok"] else "needs_review",
                           {"exit_code": result["exit_code"]})
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=f"全文修复编排器 v{SKILL_VERSION}")
    ap.add_argument("project")
    ap.add_argument("command", choices=("prepare", "apply-mechanical", "verify", "cycle"))
    ap.add_argument("--full", action="store_true", help="verify 时启用 full_review strict")
    ap.add_argument("--apply", action="store_true", help="显式授权正文机械写入；没有此参数绝不修改正文")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print("[✗] 项目目录不存在")
        return 2
    try:
        if args.command == "prepare":
            plan, path = prepare(root)
            result = {"ok": True, "plan": str(path), "issue_count": len(plan["issues"]), "write_skipped": True}
        elif args.command == "apply-mechanical":
            if not args.apply:
                print("[✗] apply-mechanical 默认只读；要修改正文必须显式提供 --apply")
                return 2
            files = resolve_targets(root)
            result = apply_mechanical(root, files)
        elif args.command == "verify":
            result = verify(root, args.full)
        else:
            plan, path = prepare(root)
            if not args.apply:
                result = {"ok": True, "plan": str(path), "write_skipped": True, "reason": "missing --apply"}
            else:
                files = resolve_targets(root)
                applied = apply_mechanical(root, files)
                checked = verify(root, args.full)
                result = {"plan": str(path), "apply": applied, "verify": checked, "ok": bool(checked["ok"])}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[✗] 修复编排失败：{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
