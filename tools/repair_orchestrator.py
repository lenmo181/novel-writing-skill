# -*- coding: utf-8 -*-
"""全文修复编排器（v7.50）。

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
import fix_said_tags
import repair_runner
from canonical_parser import chapter_files

QUEUE = Path("mind") / "全文审稿队列.json"
PLAN = Path("mind") / "全文修复任务包.json"
MECHANICAL_HINTS = ("他说：", "她说：", "光杆说", "说道", "机械问题", "文字墙", "元信息残留", "格式残留")

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

def discover_mechanical_candidates(root, round_no, wont_fix_chapters=frozenset()):
    """使用机械修复器 dry-run 探测可安全处理的章节；只写入任务包，不修改正文。

    v7.47：wont_fix_chapters——用户明确标记"不修了"的章号集合，机械候选
    发现阶段即跳过。此前 wont_fix 保护靠 prepare 的 loc 混同去重"意外"达成
    （R1 修复移除混同去重后必须显式实现，否则 wont_fix 章会被机械修复触碰）。
    """
    candidates = []
    for number, path in chapter_files(root):
        if number in wont_fix_chapters:
            continue
        try:
            result = fix_said_tags.process(str(path), True, None, True, True)
        except (OSError, UnicodeDecodeError):
            continue
        changed = bool(result[6])
        if not changed:
            continue
        tags_same, suffix, drop, beats, meta, walls = result[:6]
        details = []
        if tags_same or suffix or drop or beats:
            details.append(f"说类引导={tags_same + suffix + drop + beats}")
        if meta:
            details.append(f"元信息={meta}")
        if walls:
            details.append(f"文字墙={walls}")
        # v7.47：issue_id 加文件级短哈希后缀——重复章号（第12章旧稿/修订）时
        # 原编号两条候选同 ID，repair_runner.find_issue 只返回第一条
        stamp = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:4]
        candidates.append({
            "issue_id": f"MECH-{round_no:02d}-{number:03d}-{stamp}",
            "level": "P2",
            "cat": "单章",
            "loc": f"第{number}章",
            "msg": "机械修复候选：" + "；".join(details),
            "evidence": f"fix_said_tags dry-run：{path.name}",
            "recommended_action": "fix_said_tags.py --files --walls --meta",
            "repair_scope": str(path.relative_to(root)),
            "forbidden_action": "禁止整章重写；先快照后最小范围修复",
            "status": "open",
            "repair_mode": "mechanical_candidate",
            "verification": ["chapter_diff.py", "check_chapter.py", "full_review.py"]
        })
    return candidates

def prepare(root):
    queue = load_queue(root)
    issues = queue.get("issues") or []
    round_no = int(queue.get("round") or 1)
    # v7.47：收集 wont_fix 章号——机械候选发现阶段跳过，尊重用户"这章不修了"的决定
    wont_fix_chapters = set()
    for item in issues:
        if item.get("status") == "wont_fix":
            wont_fix_chapters.update(int(x) for x in re.findall(r"第\s*(\d{1,6})\s*章", str(item.get("loc", ""))))
    mechanical = discover_mechanical_candidates(root, round_no, wont_fix_chapters)
    # v7.47：机械候选只在机械候选之间去重——此前与 full_review 队列项按裸 loc 混同
    # 去重，而机械候选只会出现在有问题的章节、这些章几乎总已被入队（命中率近 100%），
    # 导致 apply-mechanical 几乎永远空转，机械修复管线事实死亡
    mech_locs, extra = set(), []
    for item in mechanical:
        if item["loc"] in mech_locs:
            continue
        mech_locs.add(item["loc"])
        extra.append(item)
    issues_with_repairs = issues + extra
    plan = {
        "version": SKILL_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "round": round_no,
        "project": str(root),
        "snapshot_required": True,
        "write_authorization_required": True,
        "queue_sha256": queue_sha256(root),
        "issues": [
            {**issue, "repair_mode": issue.get("repair_mode") or classify(issue),
             "verification": ["check_chapter.py", "chapter_diff.py", "continuity_check.py", "full_review.py"]}
            for issue in issues_with_repairs
        ],
    }
    target = root / PLAN
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_log.append_event(root, "repair_plan_created", str(PLAN), "open", {"queue_issue_count": len(issues), "mechanical_candidate_count": len(mechanical), "plan_issue_count": len(issues_with_repairs)})
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
        raise ValueError("修复队列已变化：当前队列与 prepare 时不一致，拒绝直接写入；请重新 prepare 后重试")
    # v7.47：章节目录回退与 full_review.py 对齐——无 书稿/ 目录时用项目根本身，
    # 此前章节放在项目根的项目机械修复 glob 恒为空
    book_dir = root / "书稿"
    base = book_dir if book_dir.is_dir() else root
    targets = []
    seen = set()
    for issue in plan.get("issues", []):
        if issue.get("repair_mode") != "mechanical_candidate":
            continue
        if issue.get("status", "open") not in {"open", "reopened"}:
            continue
        loc = str(issue.get("loc", ""))
        chapter_nums = {int(x) for x in re.findall(r"第\s*(\d{1,6})\s*章", loc)}
        for number in sorted(chapter_nums):
            matches = sorted(base.glob(f"第{number:03d}章*"))
            matches += sorted(base.glob(f"第{number}章*"))
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
    # 进程 exit=0 只代表修复器执行完，不代表病灶已经消失。
    # “auto_fixed” 只在后续 verify 成功后由 cycle 单独登记。
    audit_log.append_event(root, "mechanical_repair", str(root / "书稿"), "applied",
                           {"snapshot": str(snap), "exit_code": result["exit_code"],
                            "files": [str(p.relative_to(root)) for p in files]})
    return {"snapshot": str(snap), "files": [str(p) for p in files], "repair": result}

def verify(root, full=False):
    # v7.47：补 --no-write——此前 verify 触发 full_review 完整写路径（队列 round+1
    # 全量重建、issue_id 全换、报告覆写），命令名暗示只读实为最重写操作，
    # 且与 chapter_readiness.py:113 的全文审稿 Gate 策略直接矛盾；
    # mark-fixed 标记中途跑一次 verify 即令全部标记对不上号
    command = [sys.executable, str(Path(__file__).resolve().parent / "full_review.py"),
               str(root), "--json", "--no-write"]
    if full:
        command.insert(-1, "--strict")
    result = run_cmd(command, root)
    audit_log.append_event(root, "repair_verification", str(QUEUE), "verified" if result["ok"] else "needs_review",
                           {"exit_code": result["exit_code"]})
    return result

def register_mechanical_fixes(root, plan):
    """v7.47：把本次 apply 的机械候选项以 status=auto_fixed 登记进队列（P2-1 修复）。
    此前 auto_fixed 只进审计日志——full_review 二审只读队列不读日志，
    机械修复成果在状态机与回归记忆中完全无痕（注释承诺的"cycle 单独登记"从未实现）。"""
    mech_issues = [i for i in plan.get("issues", [])
                   if i.get("repair_mode") == "mechanical_candidate"]
    if not mech_issues:
        return 0
    try:
        path, doc = repair_runner.load_queue(root)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0
    known = {i.get("issue_id") for i in doc.get("issues") or []}
    added = 0
    for issue in mech_issues:
        if issue["issue_id"] in known:
            continue
        doc.setdefault("issues", []).append({**issue, "status": "auto_fixed"})
        added += 1
    if added:
        repair_runner.save_queue(path, doc)
    return added

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
                # v7.47：verify 前先把机械修复成果以 auto_fixed 登记进队列，
                # 让后续 full_review 二审把它们当"上轮已修复"处理（resolved_log/回归记忆生效）
                registered = register_mechanical_fixes(root, plan)
                checked = verify(root, args.full)
                verified_status = "auto_fixed" if checked["ok"] else "open"
                audit_log.append_event(root, "mechanical_repair_verified", str(QUEUE), verified_status,
                                       {"exit_code": checked["exit_code"], "snapshot": applied.get("snapshot"),
                                        "registered_auto_fixed": registered})
                # v7.47：ok 不再只等于 full_review 退出码（未传 --full 时有 P0 也返回 0，
                # 导致"什么都没修也报成功"）——要求实际修复执行成功且确有文件被处理
                result = {"plan": str(path), "apply": applied, "verify": checked,
                          "ok": bool(checked["ok"]) and bool(applied["repair"]["ok"]) and bool(applied["files"]),
                          "registered_auto_fixed": registered}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[✗] 修复编排失败：{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
