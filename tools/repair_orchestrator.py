# -*- coding: utf-8 -*-
"""全文修复编排器（v7.37）。

职责：快照 -> 读取 full_review 队列 -> 生成 AI/机械修复任务包 -> 可选执行已有机械修复器 -> 复检。
默认只生成任务包，不改正文。任何写操作都需要显式 --apply-mechanical，并先创建包含书稿的快照。
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SKILL_VERSION
import snapshot_project
import audit_log

QUEUE=Path("mind")/"全文审稿队列.json"
PLAN=Path("mind")/"全文修复任务包.json"

MECHANICAL_HINTS=("他说：", "她说：", "说道", "文字墙", "元信息残留", "格式残留")

def load_queue(root):
    path=root/QUEUE
    if not path.is_file(): raise FileNotFoundError(f"不存在全文审稿队列：{path}")
    return json.loads(path.read_text(encoding="utf-8"))

def classify(issue):
    msg=issue.get("msg","")
    mechanical=any(token in msg for token in MECHANICAL_HINTS)
    return "mechanical_candidate" if mechanical else "ai_assisted"

def prepare(root):
    queue=load_queue(root)
    issues=queue.get("issues") or []
    plan={"version":SKILL_VERSION,"generated_at":datetime.now().astimezone().isoformat(timespec="seconds"),"round":queue.get("round"),"project":str(root),"snapshot_required":True,"issues":[{**issue,"repair_mode":classify(issue),"verification":["check_chapter.py","chapter_diff.py","continuity_check.py","full_review.py"]} for issue in issues]}
    target=root/PLAN; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    audit_log.append_event(root,"repair_plan_created",str(PLAN),"open",{"issue_count":len(issues)})
    return plan,target

def run_cmd(command,root):
    try:
        p=subprocess.run(command,cwd=str(root),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=600)
        return {"ok":p.returncode==0,"exit_code":p.returncode,"tail":(p.stdout+"\n"+p.stderr).strip().splitlines()[-8:]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {"ok":False,"exit_code":2,"tail":[str(exc)]}

def apply_mechanical(root):
    snap,_=snapshot_project.create_snapshot(root,"pre-repair-mechanical",include_chapters=True)
    result=run_cmd([sys.executable,str(Path(__file__).resolve().parent/"fix_said_tags.py"),str(root/"书稿"),"--walls","--meta"],root)
    audit_log.append_event(root,"mechanical_repair",str(root/"书稿"),"auto_fixed" if result["ok"] else "open",{"snapshot":str(snap),"exit_code":result["exit_code"]})
    return {"snapshot":str(snap),"repair":result}

def verify(root,full=False):
    command=[sys.executable,str(Path(__file__).resolve().parent/"full_review.py"),str(root),"--json"]
    if full: command.insert(-1,"--strict")
    result=run_cmd(command,root)
    audit_log.append_event(root,"repair_verification",str(QUEUE),"verified" if result["ok"] else "needs_review",{"exit_code":result["exit_code"]})
    return result

def main(argv=None):
    ap=argparse.ArgumentParser(description=f"全文修复编排器 v{SKILL_VERSION}")
    ap.add_argument("project")
    ap.add_argument("command",choices=("prepare","apply-mechanical","verify","cycle"))
    ap.add_argument("--full",action="store_true",help="verify 时启用 full_review strict")
    ap.add_argument("--json",action="store_true")
    args=ap.parse_args(argv)
    root=Path(args.project).expanduser().resolve()
    if not root.is_dir(): print("[✗] 项目目录不存在"); return 2
    try:
        if args.command=="prepare":
            plan,path=prepare(root); result={"ok":True,"plan":str(path),"issue_count":len(plan["issues"])}
        elif args.command=="apply-mechanical": result=apply_mechanical(root)
        elif args.command=="verify": result=verify(root,args.full)
        else:
            plan,path=prepare(root); applied=apply_mechanical(root); checked=verify(root,args.full); result={"plan":str(path),"apply":applied,"verify":checked,"ok":bool(checked["ok"])}
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(f"[✗] 修复编排失败：{exc}"); return 2
    print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get("ok") else 1

if __name__=="__main__": raise SystemExit(main())
