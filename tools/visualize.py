#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visualize.py — 小说项目可视化看板生成器（v7.12，纯标准库）

扫 <项目根>/书稿/ + mind/ 全部档案，生成单文件离线看板 <项目根>/看板.html
（记忆中心式布局：总览/章节快照/人物状态/伏笔追踪/时间线/事件锚点/检测报告/档案库）。
设计借鉴 QMAI 记忆中心与 awesome-novel-agent 节奏预警，实现为本技能自有轻量版。

用法：
    python tools/visualize.py "<项目根>"           # 生成 看板.html 并自动打开浏览器
    python tools/visualize.py "<项目根>" --no-open # 只生成不打开

退出码：0=生成成功；2=项目根不存在或缺 书稿/ 与 mind/（非阻塞工具，永不因档案缺失报错）。
"""
import argparse
import glob
import json
import os
import re
import sys
import webbrowser
from datetime import datetime

# ---------------------------------------------------------------- 数据采集

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def md_tables(text):
    """解析 markdown 表格 → [(header_cells, rows)]，行内 | 计数不一致时按表头截断/补空。"""
    tables, cur = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells) and cells:
                continue  # 分隔行
            cur.append(cells)
        else:
            if len(cur) >= 2:
                tables.append((cur[0], cur[1:]))
            cur = []
    if len(cur) >= 2:
        tables.append((cur[0], cur[1:]))
    return tables


def table_with_header(text, *keywords):
    """找第一个表头同时含全部关键词的表格 → rows（已按表头宽度规整）。"""
    for header, rows in md_tables(text):
        if all(k in header for k in keywords):
            fixed = []
            for r in rows:
                r = (r + [""] * len(header))[: len(header)]
                fixed.append(r)
            return fixed
    return []


def scan_chapters(root):
    """书稿/ 章文件 → [{no, title, file, chars}]"""
    out = []
    pat = re.compile(r"^第(\d+)章_(.+)\.md$")
    for p in sorted(glob.glob(os.path.join(root, "书稿", "第*章_*.md"))):
        m = pat.match(os.path.basename(p))
        if not m:
            continue
        txt = read_text(p)
        chars = len(re.sub(r"\s", "", txt))
        out.append({"no": int(m.group(1)), "title": m.group(2),
                    "file": os.path.basename(p), "chars": chars})
    return out


def scan_anchors(mind):
    """锚点日志：`第X章 | 类别 | 内容 | 人物?` → [{no, cat, text, who}]"""
    out = []
    txt = read_text(os.path.join(mind, "锚点日志.md"))
    for line in txt.splitlines():
        m = re.match(r"^\s*第(\d+)章\s*\|\s*(.+)$", line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split("|")]
        cat = parts[0] if parts else ""
        body = parts[1] if len(parts) > 1 else ""
        who = parts[2] if len(parts) > 2 else ""
        out.append({"no": int(m.group(1)), "cat": cat, "text": body, "who": who})
    return out


def scan_timeline(mind):
    """时间线：`第X章 | 故事内时间 | 说明` → [{no, when, note}]"""
    out = []
    txt = read_text(os.path.join(mind, "时间线.md"))
    for line in txt.splitlines():
        m = re.match(r"^\s*第(\d+)章\s*\|\s*(.+)$", line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split("|")]
        out.append({"no": int(m.group(1)),
                    "when": parts[0] if parts else "",
                    "note": parts[1] if len(parts) > 1 else ""})
    return out


def scan_characters(mind):
    """角色状态快照：## 角色名 + - 字段：值 → [{name, fields:[{k,v}]}]"""
    out, cur = [], None
    txt = read_text(os.path.join(mind, "角色状态快照.md"))
    for line in txt.splitlines():
        if line.startswith("## "):
            cur = {"name": line[3:].strip(), "fields": []}
            out.append(cur)
        elif cur is not None and line.strip().startswith(("-", "*")):
            item = line.strip().lstrip("-*").strip()
            k, sep, v = item.partition("：")
            cur["fields"].append({"k": (k if sep else "").strip() or "状态",
                                  "v": (v if sep else item).strip()})
    return out


def scan_foreshadow(mind):
    rows = table_with_header(read_text(os.path.join(mind, "伏笔追踪表.md")), "编号")
    out = []
    for r in rows:
        status = r[5] if len(r) > 5 else ""
        if status.startswith("未埋"):
            state = "未埋"
        elif "已收" in status or "已回收" in status:
            state = "已回收"
        else:
            state = "推进中"
        out.append({"id": r[0], "content": r[1] if len(r) > 1 else "",
                    "planted": r[2] if len(r) > 2 else "",
                    "payoff": r[3] if len(r) > 3 else "",
                    "tier": r[4] if len(r) > 4 else "", "status": status, "state": state})
    return out


def scan_decisions(mind):
    rows = table_with_header(read_text(os.path.join(mind, "剧情走向锁定.md")), "日期")
    return [{"date": r[0], "decision": r[1], "source": r[2]} for r in rows]


def scan_scores(mind):
    """朱雀/墨尺报告：5列且首列为整数的行视为单章结果（章|人类分|AI%|疑似%|处置），
    同章以后出现的为准（报告按时间追加）；另兜底匹配散文行「第X章…人类分 N」。
    → {"朱雀": {ch: {...}}, "墨尺": {...}}"""
    result = {}

    def _f(cell):
        return float(re.sub(r"[*\s]", "", cell))

    for name, fname in (("朱雀", "朱雀检测报告.md"), ("墨尺", "墨尺检测报告.md")):
        txt = read_text(os.path.join(mind, fname))
        scores = {}
        for m in re.finditer(r"第(\d+)章[^\n]*?人类分\s*\*{0,2}(\d+(?:\.\d+)?)\*{0,2}", txt):
            scores[int(m.group(1))] = {"human": float(m.group(2)), "ai": None, "sus": None}
        for header, rows in md_tables(txt):
            if "人类分" not in header:
                continue
            for r in rows:
                if len(r) != 5 or not re.fullmatch(r"\d{1,4}", re.sub(r"[*\s]", "", r[0])):
                    continue
                try:
                    scores[int(re.sub(r"[*\s]", "", r[0]))] = {
                        "human": _f(r[1]), "ai": _f(r[2]), "sus": _f(r[3])}
                except ValueError:
                    continue
        result[name] = scores
    return result


def rhythm_warnings(types):
    """节奏预警（对齐 grep_consistency D类口径）：同类连续≥3章；缓冲-xx 合计连续≥4章。"""
    warns = []
    run, run_val = 1, None
    run_buf = 0
    for i, t in enumerate(types + [None]):
        val = (t or "").strip()
        if val == run_val and val:
            run += 1
            run_buf += 1 if val.startswith("缓冲") else 0
        else:
            if run_val:
                if run >= 3:
                    warns.append(f"第{i-run+1}-{i}章连续 {run} 章「{run_val}」")
                elif run_buf >= 4:
                    warns.append(f"第{i-run+1}-{i}章连续缓冲章合计 {run_buf} 章")
            run, run_val, run_buf = 1, val, 1 if val.startswith("缓冲") else 0
    return [w for w in warns if w]


def collect(root):
    mind = os.path.join(root, "mind")
    data = {"root": os.path.basename(root.rstrip("\\/")) or root,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "chapters": scan_chapters(root)}
    toc = table_with_header(read_text(os.path.join(mind, "章节目录.md")), "章号", "标题")
    toc_map = {}
    for r in toc:
        try:
            toc_map[int(r[0])] = {"title": r[1], "chars": r[2], "type": r[3],
                                  "check": r[4], "date": r[5]}
        except (ValueError, IndexError):
            continue
    for ch in data["chapters"]:
        row = toc_map.get(ch["no"], {})
        ch["title"] = row.get("title") or ch["title"]
        ch["type"] = row.get("type", "")
        ch["check"] = row.get("check", "")
        ch["date"] = row.get("date", "")
        m = re.search(r"AI味(\d+)\s*/\s*10", ch["check"])
        ch["aiidx"] = int(m.group(1)) if m else None
    data["toc_orphan"] = [n for n in toc_map if n not in {c["no"] for c in data["chapters"]}]
    data["anchors"] = scan_anchors(mind)
    data["timeline"] = scan_timeline(mind)
    data["characters"] = scan_characters(mind)
    data["foreshadow"] = scan_foreshadow(mind)
    data["decisions"] = scan_decisions(mind)
    data["scores"] = scan_scores(mind)
    data["rhythm_warn"] = rhythm_warnings([c["type"] for c in data["chapters"]])
    raw_files = []
    for base, dirs, files in os.walk(mind):
        dirs[:] = [d for d in dirs if d != "检测备份"]
        for f in sorted(files):
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(base, f), mind).replace("\\", "/")
                raw_files.append({"name": rel, "text": read_text(os.path.join(base, f))})
    data["files"] = raw_files
    return data

# ---------------------------------------------------------------- HTML 模板

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>看板 · __TITLE__</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--line:#e8eaee;--ink:#1f2329;--sub:#6b7280;--acc:#2f6fed;--ok:#16a34a;--warn:#d97706;--bad:#dc2626}
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.65 "Microsoft YaHei","PingFang SC",system-ui,sans-serif;background:var(--bg);color:var(--ink);display:flex;min-height:100vh}
nav{width:210px;background:var(--card);border-right:1px solid var(--line);padding:18px 10px;position:sticky;top:0;height:100vh;overflow:auto;flex-shrink:0}
nav h1{font-size:16px;padding:0 10px 14px;border-bottom:1px solid var(--line);margin-bottom:12px;word-break:break-all}
nav h1 small{display:block;font-size:11px;color:var(--sub);font-weight:normal;margin-top:3px}
nav a{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-radius:8px;color:var(--ink);text-decoration:none;margin:2px 0}
nav a:hover{background:#f0f3fa}
nav a.on{background:#e8effd;color:var(--acc);font-weight:600}
nav a .n{font-size:11px;color:var(--sub);background:#f1f2f4;border-radius:9px;padding:1px 7px}
nav a.on .n{background:#d8e4fb;color:var(--acc)}
main{flex:1;padding:22px 26px;max-width:1080px;min-width:0}
section{display:none}.section.on{display:block}
h2{font-size:17px;margin-bottom:14px}
h2 small{font-size:12px;color:var(--sub);font-weight:normal;margin-left:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
.stat b{display:block;font-size:21px;margin-top:2px}
.stat span{font-size:12px;color:var(--sub)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px;margin-bottom:12px}
.card h3{font-size:15px;margin-bottom:8px}
.badge{display:inline-block;font-size:11px;border-radius:9px;padding:1px 9px;margin-left:6px;vertical-align:1px;background:#f1f2f4;color:var(--sub)}
.badge.t{background:#e8effd;color:var(--acc)}.badge.g{background:#dcfce7;color:var(--ok)}.badge.y{background:#fef3c7;color:var(--warn)}.badge.r{background:#fee2e2;color:var(--bad)}.badge.p{background:#f3e8ff;color:#7c3aed}
.muted{color:var(--sub);font-size:12px}
.kv{margin:3px 0}.kv .k{color:var(--sub);margin-right:6px;white-space:nowrap}
.warnbox{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13px}
.empty{color:var(--sub);text-align:center;padding:40px 0}
input,select{border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;background:#fff;margin:0 8px 12px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:600;background:#fafbfc;white-space:nowrap}
.snap{border-left:3px solid var(--acc)}
.anchor{margin:5px 0;padding-left:10px;border-left:2px solid var(--line)}
.tl{border-left:2px solid var(--line);margin-left:8px;padding-left:20px}
.tl .item{position:relative;padding-bottom:14px}
.tl .item::before{content:"";position:absolute;left:-26px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--acc);border:2px solid #fff;box-shadow:0 0 0 1px var(--line)}
pre.raw{white-space:pre-wrap;word-break:break-word;font:12px/1.7 Consolas,monospace;background:#fafbfc;border:1px solid var(--line);border-radius:10px;padding:14px;max-height:70vh;overflow:auto}
footer{color:var(--sub);font-size:11px;margin-top:26px}
</style></head><body>
<nav><h1 id="bkTitle"></h1><div id="nav"></div></nav>
<main id="main"></main>
<script>
const D = __DATA__;
const esc = s => String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bold = s => esc(s).replace(/\\*\\*(.+?)\\*\\*/g,"<b>$1</b>");
const H = {"朱雀":90};
function badgeCls(v){return v>=H["朱雀"]?"g":v>=80?"y":"r";}
// 最小 markdown 渲染：标题/表格/列表/引用/粗体/分隔线
function md(t){
  const lines=String(t||"").split("\\n");let out=[],i=0;
  const inline=s=>bold(s).replace(/`([^`]+)`/g,"<code>$1</code>");
  while(i<lines.length){
    const L=lines[i];
    if(/^\\s*\\|.*\\|\\s*$/.test(L)){
      let rows=[];while(i<lines.length&&/^\\s*\\|.*\\|\\s*$/.test(lines[i])){
        const cells=lines[i].trim().replace(/^\\||\\|$/g,"").split("|").map(c=>c.trim());
        if(!cells.every(c=>/^:?-{2,}:?$/.test(c)))rows.push(cells);i++;}
      if(rows.length){out.push("<table><tr>"+rows[0].map(c=>"<th>"+inline(c)+"</th>").join("")+"</tr>");
        rows.slice(1).forEach(r=>out.push("<tr>"+r.map(c=>"<td>"+inline(c)+"</td>").join("")+"</tr>"));out.push("</table>");}
      continue;}
    if(/^#{1,4}\\s/.test(L)){const lv=Math.min(L.match(/^#+/)[0].length+1,5);out.push(`<h${lv}>`+inline(L.replace(/^#+\\s*/,""))+`</h${lv}>`);}
    else if(/^---+\\s*$/.test(L))out.push("<hr style='border:none;border-top:1px solid var(--line);margin:10px 0'>");
    else if(/^\\s*[-*]\\s/.test(L))out.push("<div class='kv'>· "+inline(L.replace(/^\\s*[-*]\\s*/,""))+"</div>");
    else if(/^>\\s?/.test(L))out.push("<div class='muted'>"+inline(L.replace(/^>\\s?/,""))+"</div>");
    else if(L.trim())out.push("<p style='margin:4px 0'>"+inline(L)+"</p>");
    i++;}
  return out.join("\\n");
}
function scoreBadge(ch){
  const s=D.scores["朱雀"][ch],m=D.scores["墨尺"][ch];
  if(s)return `<span class="badge ${badgeCls(s.human)}"${s.ai!=null?` title="AI ${s.ai}% / 疑似 ${s.sus}%"`:""}>朱雀 ${s.human}</span>`;
  if(m)return `<span class="badge ${badgeCls(m.human)}">墨尺 ${m.human}</span>`;
  return "";}
function chart(){
  const chs=D.chapters.map(c=>c.no),sv=chs.map(n=>(D.scores["朱雀"][n]||{}).human);
  if(!sv.some(v=>v!=null))return "<div class='empty'>暂无朱雀检测数据（跑 tools/zhuque_check.py --book 后刷新）</div>";
  const W=760,Hh=210,pad=34,bw=(W-pad*2)/Math.max(chs.length-1,1);
  const y=v=>Hh-pad-(v/100)*(Hh-pad*2);
  let s=`<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;background:var(--card);border:1px solid var(--line);border-radius:12px">`;
  [[90,"var(--ok)","90 达标线"],[80,"var(--warn)","80 警戒线"]].forEach(([lv,c,t])=>{s+=`<line x1="${pad}" y1="${y(lv)}" x2="${W-pad}" y2="${y(lv)}" stroke="${c}" stroke-dasharray="4 4" stroke-width="1"/><text x="${W-pad+2}" y="${y(lv)+4}" font-size="10" fill="${c}">${t}</text>`;});
  let pts=[];
  chs.forEach((n,i)=>{const v=sv[i];if(v==null)return;const x=pad+i*bw,yy=y(v);pts.push([x,yy]);
    s+=`<circle cx="${x}" cy="${yy}" r="3.5" fill="${v>=90?"var(--ok)":v>=80?"var(--warn)":"var(--bad)"}"/><text x="${x}" y="${yy-8}" font-size="10" text-anchor="middle" fill="var(--sub)">${v}</text><text x="${x}" y="${Hh-10}" font-size="10" text-anchor="middle" fill="var(--sub)">${n}</text>`;});
  if(pts.length>1)s+=`<polyline points="${pts.map(p=>p.join(",")).join(" ")}" fill="none" stroke="var(--acc)" stroke-width="1.5" opacity="0.6"/>`;
  return s+"</svg><div class='muted' style='margin-top:4px'>朱雀人类分走势（人工占比，≥90 达标 / 80-89 警告 / &lt;80 禁止交付）</div>";
}
const anchorsOf=no=>D.anchors.filter(a=>a.no===no);
const tlOf=no=>D.timeline.find(t=>t.no===no);
const SECTIONS=[
 {id:"ov",name:"总览",f:()=>{
   const chs=D.chapters,total=chs.reduce((s,c)=>s+(c.chars||0),0),last=chs[chs.length-1];
   const zs=Object.entries(D.scores["朱雀"]).map(([n,v])=>[+n,v.human]);const lz=zs.length?zs[zs.length-1]:null;
   const fb={推进中:0,未埋:0,已回收:0};D.foreshadow.forEach(f=>fb[f.state]=(fb[f.state]||0)+1);
   return `<div class="grid">
    <div class="stat"><span>章节</span><b>${chs.length}</b></div>
    <div class="stat"><span>总字数</span><b>${(total/10000).toFixed(1)}万</b></div>
    <div class="stat"><span>最新章</span><b style="font-size:15px">${last?`第${last.no}章 ${esc(last.title)}`:"—"}</b></div>
    <div class="stat"><span>朱雀最新</span><b style="color:${lz?(lz[1]>=90?"var(--ok)":lz[1]>=80?"var(--warn)":"var(--bad)"):"var(--sub)"}">${lz?lz[1]:"—"}</b></div>
    <div class="stat"><span>伏笔 推进中/未埋</span><b>${fb.推进中||0} / ${fb.未埋||0}</b></div>
    <div class="stat"><span>事件锚点</span><b>${D.anchors.length}</b></div></div>`
   +(D.rhythm_warn.length?`<div class="warnbox">⚖ 节奏预警：${D.rhythm_warn.map(esc).join("；")}</div>`:"")
   +`<div class="card"><h3>朱雀人类分走势</h3>${chart()}</div>`
   +(D.decisions.length?`<div class="card"><h3>最新锁定决策</h3>${D.decisions.slice(-3).reverse().map(d=>`<div class="kv"><span class="k">${esc(d.date)}</span>${bold(d.decision)} <span class="muted">（${esc(d.source)}）</span></div>`).join("")}</div>`:"");
 }},
 {id:"ch",name:"章节快照",n:D.chapters.length,f:()=>{
   if(!D.chapters.length)return "<div class='empty'>书稿/ 下暂无章节</div>";
   return D.chapters.slice().reverse().map(c=>{
     const an=anchorsOf(c.no),t=tlOf(c.no);
     return `<div class="card snap"><h3>第${c.no}章 ${esc(c.title)}
       ${c.type?`<span class="badge t">${esc(c.type)}</span>`:""}${scoreBadge(c.no)}
       <span class="badge">${c.chars||c.chars===0?c.chars+"字":""}</span>${c.date?`<span class="badge">${esc(c.date)}</span>`:""}</h3>
       ${c.check?`<div class="muted">${esc(c.check)}</div>`:""}
       ${an.length?an.map(a=>`<div class="anchor"><span class="badge p">${esc(a.cat)}</span> ${bold(a.text)}${a.who?` <span class="muted">〔${esc(a.who)}〕</span>`:""}</div>`).join(""):""}
       ${t?`<div class="kv" style="margin-top:6px"><span class="k">⏱ ${esc(t.when)}</span>${esc(t.note)}</div>`:""}
     </div>`;}).join("");
 }},
 {id:"pc",name:"人物状态",n:D.characters.length,f:()=>{
   return `<input id="pcQ" placeholder="搜索角色/字段…" oninput="pcFilter(this.value)">`+`<div id="pcList">`
   +(D.characters.length?D.characters.map(p=>`<div class="card pc" data-s="${esc(p.name+" "+p.fields.map(f=>f.k+f.v).join(" "))}">
     <h3>${esc(p.name)}</h3>${p.fields.map(f=>`<div class="kv"><span class="k">${esc(f.k)}</span>${bold(f.v)}</div>`).join("")}</div>`).join(""):"<div class='empty'>mind/角色状态快照.md 不存在或为空</div>")+"</div>";
 }},
 {id:"fb",name:"伏笔追踪",n:D.foreshadow.length,f:()=>{
   if(!D.foreshadow.length)return "<div class='empty'>mind/伏笔追踪表.md 不存在或为空</div>";
   const st={"推进中":"t","未埋":"y","已回收":"g"};
   return `<div class="card"><table><tr><th>编号</th><th>内容</th><th>埋设</th><th>预计回收</th><th>Tier</th><th>状态</th></tr>`
   +D.foreshadow.map(x=>`<tr><td><b>${esc(x.id)}</b></td><td>${bold(x.content)}</td><td>${esc(x.planted)}</td><td>${esc(x.payoff)}</td><td>${esc(x.tier)}</td><td><span class="badge ${st[x.state]||""}">${esc(x.status)}</span></td></tr>`).join("")
   +"</table></div>";
 }},
 {id:"tl",name:"时间线",n:D.timeline.length,f:()=>{
   if(!D.timeline.length)return "<div class='empty'>mind/时间线.md 不存在或为空</div>";
   return `<div class="tl">`+D.timeline.slice().sort((a,b)=>a.no-b.no).map(t=>`<div class="item"><b>第${t.no}章</b> <span class="badge">${esc(t.when)}</span><div>${esc(t.note)}</div></div>`).join("")+"</div>";
 }},
 {id:"an",name:"事件锚点",n:D.anchors.length,f:()=>{
   const cats=[...new Set(D.anchors.map(a=>a.cat))];
   return `<select id="anCat" onchange="anFilter()"><option value="">全部类别</option>${cats.map(c=>`<option>${esc(c)}</option>`).join("")}</select>`
   +`<input id="anQ" placeholder="搜索内容…" oninput="anFilter()">`
   +`<div id="anList">`+(D.anchors.length?D.anchors.slice().reverse().map(a=>`<div class="card an" data-c="${esc(a.cat)}" data-s="${esc(a.text+" "+a.who)}">
     <span class="badge t">第${a.no}章</span><span class="badge p">${esc(a.cat)}</span> ${bold(a.text)}${a.who?` <span class="muted">〔${esc(a.who)}〕</span>`:""}</div>`).join(""):"<div class='empty'>mind/锚点日志.md 不存在或为空</div>")+"</div>";
 }},
 {id:"det",name:"检测报告",f:()=>{
   const zj=D.files.find(f=>f.name==="朱雀检测报告.md"),mo=D.files.find(f=>f.name==="墨尺检测报告.md");
   return `<div class="card"><h3>分数走势</h3>${chart()}</div>`
   +(zj?`<div class="card"><h3>朱雀检测报告</h3><pre class="raw">${esc(zj.text)}</pre></div>`:"")
   +(mo?`<div class="card"><h3>墨尺检测报告</h3><pre class="raw">${esc(mo.text)}</pre></div>`:"")
   +(!zj&&!mo?"<div class='empty'>暂无检测报告</div>":"");
 }},
 {id:"arch",name:"档案库",n:D.files.length,f:()=>{
   return `<select id="archSel" onchange="archShow(this.value)">${D.files.map((f,i)=>`<option value="${i}">${esc(f.name)}</option>`).join("")}</select><div id="archView"></div>`;
 }}
];
function render(){
  document.getElementById("bkTitle").innerHTML=esc(D.root)+"<small>生成于 "+D.generated+" · 网络小说创作技能 v7.12</small>";
  document.getElementById("nav").innerHTML=SECTIONS.map((s,i)=>`<a href="#${s.id}" data-i="${i}" onclick="go(${i});return false"><span>${s.name}</span>${s.n!=null?`<span class="n">${s.n}</span>`:""}</a>`).join("");
  document.getElementById("main").innerHTML=SECTIONS.map((s,i)=>`<section id="sec${i}" class="section"><h2>${s.name}</h2>${s.f()}</section>`).join("")+"<footer>本看板由 tools/visualize.py 生成 · 数据源：书稿/ + mind/ · 改动后重跑即可刷新</footer>";
  go(0);archShow(0);
  const h=location.hash.slice(1);const idx=SECTIONS.findIndex(s=>s.id===h);if(idx>0)go(idx);
}
function go(i){
  document.querySelectorAll("nav a").forEach((a,j)=>a.classList.toggle("on",i===j));
  document.querySelectorAll(".section").forEach((s,j)=>s.classList.toggle("on",i===j));
}
function pcFilter(q){q=q.toLowerCase();document.querySelectorAll(".pc").forEach(c=>c.style.display=c.dataset.s.toLowerCase().includes(q)?"":"none");}
function anFilter(){const c=document.getElementById("anCat").value,q=(document.getElementById("anQ").value||"").toLowerCase();
  document.querySelectorAll(".an").forEach(x=>x.style.display=(x.dataset.c===c||!c)&&x.dataset.s.toLowerCase().includes(q)?"":"none");}
function archShow(i){const f=D.files[i];if(!f)return;document.getElementById("archView").innerHTML=`<div class="card">${md(f.text)}</div>`;}
render();
</script></body></html>"""

# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="生成小说项目可视化看板（看板.html）")
    ap.add_argument("root", nargs="?", default=".", help="小说项目根目录")
    ap.add_argument("--no-open", action="store_true", help="生成后不打开浏览器")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not (os.path.isdir(os.path.join(root, "书稿")) or os.path.isdir(os.path.join(root, "mind"))):
        print(f"[✗] {root} 下没有 书稿/ 或 mind/——这不是小说项目根目录", file=sys.stderr)
        return 2
    data = collect(root)
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML.replace("__DATA__", data_json).replace("__TITLE__", data["root"])
    out = os.path.join(root, "看板.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    zj = sum(1 for v in data["scores"]["朱雀"].values())
    print(f"[✓] 看板已生成：{out}")
    print(f"    章节 {len(data['chapters'])} ｜ 锚点 {len(data['anchors'])} ｜ 角色 {len(data['characters'])} "
          f"｜ 伏笔 {len(data['foreshadow'])} ｜ 朱雀数据 {zj} 章 ｜ 档案 {len(data['files'])} 份")
    if data["rhythm_warn"]:
        print(f"    [!] 节奏预警：{'；'.join(data['rhythm_warn'])}")
    if data["toc_orphan"]:
        print(f"    [!] 章节目录中有但书稿缺失的章号：{sorted(data['toc_orphan'])}")
    if not args.no_open:
        webbrowser.open("file://" + out.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
