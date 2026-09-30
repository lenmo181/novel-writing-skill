# -*- coding: utf-8 -*-
"""项目记忆检索器（v7.37）：不依赖向量数据库的本地轻量检索。"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from config import SKILL_VERSION
SEARCH_DIRS=("mind","大纲","设定",".story-review")
IGNORE_NAMES={"audit.jsonl"}

def query_terms(query: str) -> list[str]:
    raw=[x for x in re.split(r"[\s,，。；;、/|]+",query.strip()) if x]
    terms=[]
    for token in raw:
        terms.append(token)
        if len(token)>2 and all("\u4e00"<=ch<="\u9fff" for ch in token):
            terms.extend(token[i:i+2] for i in range(len(token)-1))
    return list(dict.fromkeys(terms))

def iter_files(root: Path):
    for directory in SEARCH_DIRS:
        base=root/directory
        if not base.exists(): continue
        files=[base] if base.is_file() else sorted(base.rglob("*"))
        for path in files:
            if path.is_file() and path.name not in IGNORE_NAMES and path.suffix.lower() in {".md",".txt",".json",".jsonl"}:
                yield path

def search(root: Path, query: str, limit: int=12, context: int=1) -> dict:
    terms=query_terms(query); hits=[]
    for path in iter_files(root):
        try: lines=path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError,UnicodeError): continue
        for number,line in enumerate(lines,1):
            score=sum(line.count(term) for term in terms)
            if score<=0: continue
            before=lines[max(0,number-1-context):number-1]; after=lines[number:number+context]
            hits.append({"path":str(path.relative_to(root)),"line":number,"score":score,"match_terms":[t for t in terms if t in line],"snippet":"\n".join(before+[line]+after)})
    hits.sort(key=lambda x:(-x["score"],x["path"],x["line"]))
    return {"version":SKILL_VERSION,"query":query,"terms":terms,"count":len(hits),"hits":hits[:max(1,limit)]}

def render(report):
    lines=[f"# 记忆检索（v{report['version']}）","",f"- 查询：{report['query']}",f"- 命中：{report['count']}（展示前 {len(report['hits'])} 条）",""]
    for hit in report["hits"]:
        lines.extend([f"## {hit['path']}:{hit['line']}（score={hit['score']}）","","```text",hit["snippet"],"```",""])
    if not report["hits"]: lines.append("未命中。可缩短关键词或直接指定档案路径。")
    return "\n".join(lines)

def main(argv=None):
    ap=argparse.ArgumentParser(description=f"本地项目记忆检索 v{SKILL_VERSION}")
    ap.add_argument("project"); ap.add_argument("query"); ap.add_argument("--limit",type=int,default=12); ap.add_argument("--context",type=int,default=1); ap.add_argument("--json",action="store_true")
    args=ap.parse_args(argv); root=Path(args.project).expanduser()
    if not root.is_dir() or args.limit<1 or args.context<0: print("[✗] 项目目录不存在，或参数非法"); return 2
    report=search(root,args.query,args.limit,args.context); print(json.dumps(report,ensure_ascii=False,indent=2) if args.json else render(report)); return 0

if __name__ == "__main__": raise SystemExit(main())
