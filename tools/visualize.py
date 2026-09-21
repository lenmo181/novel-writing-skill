#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visualize.py — 小说项目可视化看板生成器（v7.22，纯标准库）

扫 <项目根>/书稿/ + mind/ 全部档案，生成单文件离线看板 <项目根>/看板.html
（记忆中心式布局：总览/正文阅读/章节快照/人物状态/伏笔追踪/时间线/事件锚点/检测报告/档案库）。
v7.22 新增正文阅读模式：全部章节正文内嵌（按章懒渲染），支持续读记忆（localStorage）、
上一章/下一章（按钮+←→键盘）、字号调节、纸张/夜间/白底三主题、阅读进度条、全文搜索跳转、移动端适配。
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

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_index import collect_chapters, read_body_chars  # noqa: E402

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


def chapter_paras(txt):
    """章正文 → 段落列表：剥章题行（# 前缀或裸「第X章 …」两种格式），按空行分段，段内换行直接拼接。"""
    lines = txt.splitlines()
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines:
        first = lines[0].strip()
        if first.startswith("#"):
            lines = lines[1:]
        elif re.match(r"^第[0-9０-９一二三四五六七八九十百千两]+\s*章", first) and len(first) <= 40:
            lines = lines[1:]  # 无 # 前缀的裸章题行，剥掉防正文首段重复章名
    paras, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            paras.append("".join(cur))
            cur = []
    if cur:
        paras.append("".join(cur))
    return paras


def scan_chapters(root):
    """书稿/ 章文件 → [{no, title, file, chars, paras}]，与 gen_index 统一识别/字数口径。"""
    out = []
    book_dir = os.path.join(root, "书稿")
    if not os.path.isdir(book_dir):
        return out
    for no, fname, title in collect_chapters(book_dir):
        path = os.path.join(book_dir, fname)
        txt = read_text(path)
        out.append({"no": no, "title": title or "", "file": fname,
                    "chars": read_body_chars(path), "paras": chapter_paras(txt)})
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
    # v7.25：缺列安全取值——两列表（日期/决策）不再因 r[2] 越界导致整份看板生成失败
    return [{"date": r[0],
             "decision": r[1] if len(r) > 1 else "",
             "source": r[2] if len(r) > 2 else ""} for r in rows]


def scan_scores(mind):
    """解析当前朱雀/墨尺报告，按表头识别列，兼容不同列数与追加报告。"""
    result = {}

    def norm(cell):
        return re.sub(r"[*\s]", "", cell or "")

    def num(cell):
        s = norm(cell)
        if not s or s in {"-", "—"}:
            return None
        try:
            return float(re.sub(r"[^0-9.+-]", "", s))
        except ValueError:
            return None

    def idx(headers, names):
        for i, h in enumerate(headers):
            if h in names:
                return i
        return None

    for name, fname in (("朱雀", "朱雀检测报告.md"), ("墨尺", "墨尺检测报告.md")):
        txt = read_text(os.path.join(mind, fname))
        scores = {}
        for m in re.finditer(r"第(\d+)章[^\n]*?人类分\s*\*{0,2}(\d+(?:\.\d+)?)\*{0,2}", txt):
            scores[int(m.group(1))] = {"human": float(m.group(2)), "ai": None, "sus": None}
        for header, rows in md_tables(txt):
            headers = [norm(c) for c in header]
            ch_i = idx(headers, {"章号", "章节", "章"})
            human_i = idx(headers, {"人类分", "人类分数"})
            total_i = idx(headers, {"总分", "total"})
            ai_i = idx(headers, {"AI%", "AI", "ai_pct"})
            sus_i = idx(headers, {"疑似%", "疑似AI%", "疑似AI"})
            if ch_i is None:
                continue
            for row in rows:
                vals = [(c or "").strip() for c in row]
                if ch_i >= len(vals):
                    continue
                chapter = num(vals[ch_i])
                if chapter is None or int(chapter) != chapter:
                    continue
                human = num(vals[human_i]) if human_i is not None and human_i < len(vals) else None
                total = num(vals[total_i]) if total_i is not None and total_i < len(vals) else None
                if human is None and total is not None:
                    human = total * 10
                if human is None:
                    # v7.25：最近一轮该章检测失败（结论「失败」或整行占位符）→ 旧分数不再代表
                    # 当前状态，从走势/徽标中移除，而不是继续展示旧成功分
                    rest = [c for k2, c in enumerate(vals) if k2 != ch_i]
                    if any("失败" in c for c in rest) or all(c.strip() in {"-", "—", ""} for c in rest):
                        scores.pop(int(chapter), None)
                    continue
                scores[int(chapter)] = {
                    "human": human,
                    "ai": num(vals[ai_i]) if ai_i is not None and ai_i < len(vals) else None,
                    "sus": num(vals[sus_i]) if sus_i is not None and sus_i < len(vals) else None,
                }
        result[name] = scores
    return result


def rhythm_warnings(chapters):
    """节奏预警（v7.25 重写）：入参改为 [{no, type}]——告警章号用真实章号，且「连续」按
    章号严格递增判定（此前用列表序号当章号，第1/2/10章会被误报成「第1-3章连续」）。
    规则不变：同类连续≥3章；任意缓冲型合计连续≥4章。"""
    warns = []
    types = [c for c in chapters if (c.get("type") or "").strip()]
    i = 0
    while i < len(types):
        val = types[i]["type"].strip()
        j = i + 1
        while (j < len(types) and types[j]["type"].strip() == val
               and types[j]["no"] == types[j - 1]["no"] + 1):
            j += 1
        if j - i >= 3:
            warns.append(f"第{types[i]['no']}-{types[j - 1]['no']}章连续 {j - i} 章「{val}」")
        i = max(j, i + 1)
    i = 0
    while i < len(types):
        if not types[i]["type"].strip().startswith("缓冲"):
            i += 1
            continue
        start = i
        while (i < len(types) and types[i]["type"].strip().startswith("缓冲")
               and (i == start or types[i]["no"] == types[i - 1]["no"] + 1)):
            i += 1
        if i - start >= 4:
            warns.append(f"第{types[start]['no']}-{types[i - 1]['no']}章连续缓冲章合计 {i - start} 章")
    return warns


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
    data["rhythm_warn"] = rhythm_warnings(data["chapters"])
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
#rdProg{position:fixed;top:0;left:0;height:3px;background:var(--acc);z-index:99;width:0}
.rdbar{position:sticky;top:0;z-index:9;background:var(--bg);padding:10px 0 8px;border-bottom:1px solid var(--line);margin-bottom:12px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.rdbar select{max-width:300px;margin:0}
.rdbar .sp{flex:1}
.btn{border:1px solid var(--line);border-radius:8px;background:var(--card);padding:5px 11px;font-size:13px;cursor:pointer;color:var(--ink);white-space:nowrap}
.btn:hover{border-color:var(--acc);color:var(--acc)}
.rdwrap{max-width:800px;margin:0 auto}
.rdtitle{font-size:24px;font-weight:700;text-align:center;margin:0 0 4px;font-family:Georgia,"Noto Serif SC","Source Han Serif SC",SimSun,serif}
.rdmeta{color:var(--sub);font-size:12px;text-align:center;margin:2px 0 22px}
.rdbody{font-family:Georgia,"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,serif;font-size:19px;line-height:1.95;letter-spacing:.015em;border-radius:12px;padding:26px 32px 22px;border:1px solid var(--line)}
.rdbody p{text-indent:2em;margin:0 0 .35em;min-height:1em}
.rddata[data-thm="paper"] .rdbody{background:#f6f1e5;border-color:#e7ddc6;color:#4a3f2f}
.rddata[data-thm="night"] .rdbody{background:#181a1f;border-color:#262932;color:#c6cbd2}
.rddata[data-thm="night"] .rdtitle{color:#e8eaee}
.rddata[data-thm="night"] .rdmeta{color:#8b919e}
.rddata[data-thm="plain"] .rdbody{background:var(--card);color:var(--ink)}
.rdfoot{display:flex;gap:10px;margin:18px 0 8px}
.rdfoot button{flex:1;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--card);font-size:14px;cursor:pointer;color:var(--ink)}
.rdfoot button:hover:not(:disabled){border-color:var(--acc);color:var(--acc)}
.rdfoot button:disabled{opacity:.4;cursor:default}
mark{background:#ffe9a8;color:inherit;padding:0 1px;border-radius:2px}
.flashp{animation:rdflash 2.4s ease-out}
@keyframes rdflash{0%{background:#fff0b8}100%{background:transparent}}
.rdres{margin:10px 0 4px}
.rdres .card{padding:10px 14px;cursor:pointer;margin-bottom:8px}
.rdres .card:hover{border-color:var(--acc)}
footer{color:var(--sub);font-size:11px;margin-top:26px}
@media(max-width:900px){body{display:block}nav{width:auto;height:auto;position:static;display:flex;align-items:center;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line);padding:8px 10px;gap:2px}nav h1{display:none}nav a{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;padding:7px 10px;margin:0;flex:none}nav a .n{flex:none}main{padding:14px 12px;max-width:none}.rdbody{padding:20px 16px}.rdtitle{font-size:21px}.rdbar select{max-width:170px}}
</style></head><body>
<div id="rdProg"></div>
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
// ---------- 正文阅读器（v7.22）：续读记忆/翻章/主题/字号/全文搜索 ----------
const THEME_NAMES={paper:"纸张",night:"夜间",plain:"白底"};
const RDKEY="kbRead::"+D.root;
let RD={cur:null,pct:0,fs:19,thm:"paper"};
try{Object.assign(RD,JSON.parse(localStorage.getItem(RDKEY)||"{}"))}catch(e){}
let RD_ON=false,rdSaveT=0;
function rdSave(){clearTimeout(rdSaveT);rdSaveT=setTimeout(()=>{try{localStorage.setItem(RDKEY,JSON.stringify(RD))}catch(e){}},300)}
function openCh(no,anchor,restore){
  if(!D.chapters.length)return;
  const i=Math.max(0,D.chapters.findIndex(c=>c.no===no));
  const c=D.chapters[i],prev=D.chapters[i-1],next=D.chapters[i+1];
  RD.cur=c.no;
  const sel=document.getElementById("rdSel");if(sel)sel.value=String(i);
  const v=document.getElementById("rdView");
  const metas=[c.type?`<span class="badge t">${esc(c.type)}</span>`:"",scoreBadge(c.no),
    `<span class="badge">${c.chars||0}字</span>`,c.date?`<span class="badge">${esc(c.date)}</span>`:""].join("");
  v.innerHTML=`<div class="rdbody"><div class="rdtitle">第${c.no}章 ${esc(c.title)}</div>
    <div class="rdmeta">${metas}<div style="margin-top:4px">本书进度 第${i+1}/${D.chapters.length}章</div></div>
    ${c.paras&&c.paras.length?c.paras.map((p,j)=>`<p id="rp${j}">${esc(p)}</p>`).join(""):"<div class='empty'>本章正文为空</div>"}</div>
    <div class="rdfoot"><button ${prev?"":"disabled"} onclick="rdGo(${prev?prev.no:0})">← 上一章${prev?` · 第${prev.no}章`:""}</button>
    <button ${next?"":"disabled"} onclick="rdGo(${next?next.no:0})">${next?`下一章 · 第${next.no}章`:"已是最后一章"} →</button></div>`;
  v.dataset.thm=RD.thm;
  v.querySelector(".rdbody").style.fontSize=RD.fs+"px";
  if(anchor!=null){const el=document.getElementById("rp"+anchor);
    if(el){el.scrollIntoView();el.classList.add("flashp");}}
  else if(RD_ON&&restore&&RD.pct>0.02&&RD.pct<0.995)
    window.scrollTo(0,(document.body.scrollHeight-innerHeight)*RD.pct);
  else if(RD_ON)window.scrollTo(0,0);
  rdSave();
}
function rdGo(no){if(no==null)return;RD.pct=0;openCh(no);}
function rdNext(d){const i=D.chapters.findIndex(c=>c.no===RD.cur),j=i+d;
  if(i<0||j<0||j>=D.chapters.length)return;rdGo(D.chapters[j].no);}
function rdFs(d){RD.fs=Math.min(26,Math.max(14,RD.fs+d));
  const b=document.querySelector("#rdView .rdbody");if(b)b.style.fontSize=RD.fs+"px";rdSave();}
function rdThm(){RD.thm={paper:"night",night:"plain",plain:"paper"}[RD.thm]||"paper";
  document.getElementById("rdView").dataset.thm=RD.thm;
  document.getElementById("rdThmBtn").textContent="主题·"+THEME_NAMES[RD.thm];rdSave();}
function rdJump(no,pi){go(RD_I);openCh(no,pi!=null?pi:null,pi==null);}
function rdCont(){go(RD_I);openCh(RD.cur!=null?RD.cur:D.chapters[0].no,null,true);}
function rdSearch(){
  const q=(document.getElementById("rdQ").value||"").trim(),box=document.getElementById("rdRes");
  if(!q){box.innerHTML="";return}
  const hits=[];let truncated=false;
  outer:for(const c of D.chapters){const ps=c.paras||[];
    for(let i=0;i<ps.length;i++){const p=ps[i],lo=p.toLowerCase(),at=lo.indexOf(q.toLowerCase());
      if(at<0)continue;
      const s=Math.max(0,at-16),e=Math.min(p.length,at+q.length+34);
      const snip=(s>0?"…":"")+esc(p.slice(s,at))+"<mark>"+esc(p.slice(at,at+q.length))+"</mark>"+esc(p.slice(at+q.length,e))+(e<p.length?"…":"");
      hits.push(`<div class="card" onclick="rdJump(${c.no},${i})"><span class="badge t">第${c.no}章</span> <b>${esc(c.title)}</b> <span class="muted">¶${i+1}</span><div style="margin-top:3px">${snip}</div></div>`);
      if(hits.length>=200){truncated=true;break outer;}}}
  box.className="rdres";
  box.innerHTML=hits.length?`<div class="muted" style="margin-bottom:6px">命中 ${hits.length} 处${truncated?"（达上限已截断，可换更具体的词）":""}，点击任意结果跳转正文</div>`+hits.join("")
    :`<div class="empty">全书未找到「${esc(q)}」</div>`;
}
addEventListener("scroll",()=>{const bar=document.getElementById("rdProg");
  if(!bar)return;
  if(!RD_ON){bar.style.width="0";return}
  const h=document.body.scrollHeight-innerHeight,p=h>0?Math.min(1,scrollY/h):0;
  bar.style.width=(p*100).toFixed(1)+"%";RD.pct=p;rdSave();
},{passive:true});
addEventListener("keydown",e=>{if(!RD_ON)return;
  const tag=(e.target.tagName||"").toLowerCase();
  if(tag==="input"||tag==="select"||tag==="textarea")return;
  if(e.key==="ArrowRight")rdNext(1);else if(e.key==="ArrowLeft")rdNext(-1);});
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
   +(chs.length?`<div class="card" style="display:flex;align-items:center;gap:14px"><div style="flex:1;min-width:0"><h3>📖 ${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?`继续阅读 · 第${RD.cur}章 ${esc((chs.find(c=>c.no===RD.cur)||{}).title||"")}`:`开始阅读 · 第${chs[0].no}章 ${esc(chs[0].title)}`}</h3><div class="muted">${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?"看板记住了上次的章节和位置，点击接着读":"打开正文阅读模式：翻章/字号/护眼主题/全文搜索"}</div></div><button class="btn" style="padding:10px 18px;font-size:15px" onclick="rdCont()">${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?"继续阅读 →":"开始阅读 →"}</button></div>`:"")
   +(D.rhythm_warn.length?`<div class="warnbox">⚖ 节奏预警：${D.rhythm_warn.map(esc).join("；")}</div>`:"")
   +`<div class="card"><h3>朱雀人类分走势</h3>${chart()}</div>`
   +(D.decisions.length?`<div class="card"><h3>最新锁定决策</h3>${D.decisions.slice(-3).reverse().map(d=>`<div class="kv"><span class="k">${esc(d.date)}</span>${bold(d.decision)} <span class="muted">（${esc(d.source)}）</span></div>`).join("")}</div>`:"");
 }},
 {id:"rd",name:"正文阅读",n:D.chapters.length,f:()=>{
   if(!D.chapters.length)return "<div class='empty'>书稿/ 下暂无章节</div>";
   return `<div class="rdwrap"><div class="rdbar">
     <select id="rdSel" onchange="rdGo(D.chapters[+this.value].no)">${D.chapters.map((c,i)=>`<option value="${i}">第${c.no}章 ${esc(c.title)}</option>`).join("")}</select>
     <button class="btn" onclick="rdNext(-1)">← 上一章</button>
     <button class="btn" onclick="rdNext(1)">下一章 →</button>
     <span class="sp"></span>
     <button class="btn" onclick="rdFs(-1)" title="缩小字号">A-</button>
     <button class="btn" onclick="rdFs(1)" title="放大字号">A+</button>
     <button class="btn" id="rdThmBtn" onclick="rdThm()">主题·纸张</button>
   </div>
   <div style="display:flex;gap:8px;flex-wrap:wrap"><input id="rdQ" placeholder="全文搜索：人名 / 台词 / 任何词（回车）" onkeydown="if(event.key==='Enter')rdSearch()" style="flex:1;min-width:200px;margin:0"><button class="btn" onclick="rdSearch()">搜索</button></div>
   <div id="rdRes"></div>
   <div id="rdView" class="rddata" data-thm="paper"></div></div>`;
 }},
 {id:"ch",name:"章节快照",n:D.chapters.length,f:()=>{
   if(!D.chapters.length)return "<div class='empty'>书稿/ 下暂无章节</div>";
   return D.chapters.slice().reverse().map(c=>{
     const an=anchorsOf(c.no),t=tlOf(c.no);
     return `<div class="card snap"><h3>第${c.no}章 ${esc(c.title)}
       <a href="#rd" onclick="rdJump(${c.no})" style="float:right;font-size:12px;text-decoration:none;color:var(--acc)">📖 阅读</a>
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
const RD_I=SECTIONS.findIndex(s=>s.id==="rd");
function render(){
  document.getElementById("bkTitle").innerHTML=esc(D.root)+"<small>生成于 "+D.generated+" · 网络小说创作技能 __SKILL_VER__</small>";
  document.getElementById("nav").innerHTML=SECTIONS.map((s,i)=>`<a href="#${s.id}" data-i="${i}" onclick="go(${i});return false"><span>${s.name}</span>${s.n!=null?`<span class="n">${s.n}</span>`:""}</a>`).join("");
  document.getElementById("main").innerHTML=SECTIONS.map((s,i)=>`<section id="sec${i}" class="section"><h2>${s.name}</h2>${s.f()}</section>`).join("")+"<footer>本看板由 tools/visualize.py 生成 · 数据源：书稿/ + mind/ · 改动后重跑即可刷新 · 阅读进度存在本机浏览器（localStorage），换电脑不跟随</footer>";
  go(0);archShow(0);
  if(D.chapters.length){
    RD.cur=D.chapters.some(c=>c.no===RD.cur)?RD.cur:D.chapters[0].no;
    openCh(RD.cur,null,false);
    const tb=document.getElementById("rdThmBtn");if(tb)tb.textContent="主题·"+(THEME_NAMES[RD.thm]||"纸张");
    const v=document.getElementById("rdView");if(v)v.dataset.thm=RD.thm;}
  const h=location.hash.slice(1);const idx=SECTIONS.findIndex(s=>s.id===h);
  if(idx>0){go(idx);if(idx===RD_I)openCh(RD.cur,null,true);}
}
function go(i){
  document.querySelectorAll("nav a").forEach((a,j)=>a.classList.toggle("on",i===j));
  document.querySelectorAll(".section").forEach((s,j)=>s.classList.toggle("on",i===j));
  RD_ON=SECTIONS[i]&&SECTIONS[i].id==="rd";
  if(RD_ON&&D.chapters.length)
    window.scrollTo(0,(document.body.scrollHeight-innerHeight)*(RD.pct||0));
}
function pcFilter(q){q=q.toLowerCase();document.querySelectorAll(".pc").forEach(c=>c.style.display=c.dataset.s.toLowerCase().includes(q)?"":"none");}
function anFilter(){const c=document.getElementById("anCat").value,q=(document.getElementById("anQ").value||"").toLowerCase();
  document.querySelectorAll(".an").forEach(x=>x.style.display=(x.dataset.c===c||!c)&&x.dataset.s.toLowerCase().includes(q)?"":"none");}
function archShow(i){const f=D.files[i];if(!f)return;document.getElementById("archView").innerHTML=`<div class="card">${md(f.text)}</div>`;}
render();
</script></body></html>"""

# ---------------------------------------------------------------- 主流程

def skill_version():
    """从技能包 SKILL.md 头部读版本号（首个 vX.Y[Z]），读不到回退 v7.25。
    v7.25 新增：页脚版本不再硬编码，避免每次发版看板版本漂移。"""
    fallback = "v7.25"
    try:
        skill_md = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "SKILL.md")
        with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
            m = re.search(r"v(\d+\.\d+(?:\.\d+)?)", f.read(2000))
        return "v" + m.group(1) if m else fallback
    except OSError:
        return fallback


def apply_template(html, data_json, title, ver):
    """单遍占位符替换（v7.25）：此前链式 .replace 会让正文里恰好含 __TITLE__/__DATA__
    的段落被二次替换污染；re.sub 对已替换内容不重扫，天然免疫。"""
    return re.sub(r"__(DATA|TITLE|SKILL_VER)__",
                  lambda m: {"DATA": data_json, "TITLE": title, "SKILL_VER": ver}[m.group(1)],
                  html)


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
    html = apply_template(HTML, data_json, data["root"], skill_version())
    out = os.path.join(root, "看板.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    zj = sum(1 for v in data["scores"]["朱雀"].values())
    total_chars = sum(c["chars"] for c in data["chapters"])
    size_mb = os.path.getsize(out) / 1048576
    print(f"[✓] 看板已生成：{out}")
    print(f"    章节 {len(data['chapters'])} ｜ 锚点 {len(data['anchors'])} ｜ 角色 {len(data['characters'])} "
          f"｜ 伏笔 {len(data['foreshadow'])} ｜ 朱雀数据 {zj} 章 ｜ 档案 {len(data['files'])} 份")
    print(f"    内嵌正文 {len(data['chapters'])} 章 / {total_chars / 10000:.1f} 万字（阅读模式可全文阅读+搜索）"
          f" ｜ 看板体积 {size_mb:.1f} MB" + ("（较大，首次打开加载稍慢属正常）" if size_mb > 12 else ""))
    if data["rhythm_warn"]:
        print(f"    [!] 节奏预警：{'；'.join(data['rhythm_warn'])}")
    if data["toc_orphan"]:
        print(f"    [!] 章节目录中有但书稿缺失的章号：{sorted(data['toc_orphan'])}")
    if not args.no_open:
        webbrowser.open("file://" + out.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
