# -*- coding: utf-8 -*-
"""章节交付 Gate（v7.37）：把分散检查收敛为一个机器可消费的结果。"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from config import SKILL_VERSION

TOOLS=Path(__file__).resolve().parent

def run_gate(name, command, cwd):
    try:
        p=subprocess.run(command,cwd=str(cwd),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)
        output=(p.stdout+"\n"+p.stderr).strip().splitlines()
        return {"name":name,"ok":p.returncode==0,"exit_code":p.returncode,"tail":output[-6:]}
    except subprocess.TimeoutExpired:
        return {"name":name,"ok":False,"exit_code":2,"tail":["超过180秒未返回"]}
    except OSError as exc:
        return {"name":name,"ok":False,"exit_code":2,"tail":[str(exc)]}

def resolve_chapter(root, chapter):
    candidates=sorted((root/"书稿").glob(f"第{chapter:03d}章*"))+sorted((root/"书稿").glob(f"第{chapter}章*"))
    return next((p for p in candidates if p.is_file()),None)

def assess(root, chapter, full=False):
    target=resolve_chapter(root,chapter)
    if target is None:
        return {"version":SKILL_VERSION,"project":str(root),"chapter":chapter,"ok":False,"input_error":True,"gates":[{"name":"章节存在","ok":False,"exit_code":2,"tail":[f"未找到第{chapter}章"]}]}
    commands=[
      ("单章机械校验",[sys.executable,str(TOOLS/"check_chapter.py"),str(target)]),
      ("项目健康",[sys.executable,str(TOOLS/"project_health.py"),str(root)]),
      ("连续性检查",[sys.executable,str(TOOLS/"continuity_check.py"),str(root)]),
      ("上下文可构建",[sys.executable,str(TOOLS/"context_pack.py"),str(root),"--chapter",str(chapter),"--format","json"]),
    ]
    if full:
        commands.append(("全文审稿",[sys.executable,str(TOOLS/"full_review.py"),str(root),"--strict","--json"]))
    gates=[run_gate(n,c,root) for n,c in commands]
    return {"version":SKILL_VERSION,"project":str(root),"chapter":chapter,"target":str(target.relative_to(root)),"generated_at":datetime.now().astimezone().isoformat(timespec="seconds"),"gates":gates,"ok":all(g["ok"] for g in gates),"input_error":False}

def main(argv=None):
    ap=argparse.ArgumentParser(description=f"章节交付 Gate v{SKILL_VERSION}")
    ap.add_argument("project"); ap.add_argument("chapter",type=int); ap.add_argument("--full",action="store_true",help="额外运行全文审稿 strict")
    ap.add_argument("--json",action="store_true"); ap.add_argument("--out",default="")
    args=ap.parse_args(argv)
    root=Path(args.project).expanduser().resolve()
    if not root.is_dir() or args.chapter<1: print("[✗] 项目目录或章节号非法"); return 2
    report=assess(root,args.chapter,args.full)
    output=json.dumps(report,ensure_ascii=False,indent=2) if args.json else render(report)
    if args.out:
        target=Path(args.out).expanduser(); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(output+"\n",encoding="utf-8"); print(f"交付 Gate 已写入：{target}")
    else: print(output)
    return 2 if report.get("input_error") else (0 if report["ok"] else 1)

def render(report):
    lines=[f"# 章节交付 Gate（v{report['version']}）","",f"- 第 {report['chapter']} 章：`{report.get('target','-')}`","- 时间：{report.get('generated_at','')}","", "| Gate | 结果 | 退出码 |","|---|---|---:|"]
    for gate in report["gates"]: lines.append(f"| {gate['name']} | {'PASS' if gate['ok'] else 'REVISE'} | {gate['exit_code']} |")
    lines.extend(["",f"结论：{'PASS，可进入交付/作者验收。' if report['ok'] else 'REVISE，先处理失败 Gate。'}","", "失败 Gate 的详细输出已保留在 JSON 报告中；本工具不修改正文。"])
    return "\n".join(lines)

if __name__ == "__main__": raise SystemExit(main())
