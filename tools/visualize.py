#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visualize.py — 小说项目可视化看板生成器（v7.48，纯标准库）

扫 <项目根>/书稿/ + mind/ 全部档案，生成单文件离线看板 <项目根>/看板.html
（记忆中心式布局：总览/正文阅读/章节快照/人物状态/伏笔追踪/时间线/事件锚点/写作分析/检测报告/档案库）。
    v7.22 新增正文阅读模式：全部章节正文内嵌（按章懒渲染），支持续读记忆（localStorage）、
上一章/下一章（按钮+←→键盘）、字号调节、纸张/夜间/白底三主题、阅读进度条、全文搜索跳转、移动端适配。
    v7.48 升级为「驾驶舱」：总览改 6 张 KPI + 统一待处理预警箱；新增写作分析分区（写作热力日历 /
月度产出 / 质量矩阵 / 节奏结构 / 人物出场 / AI味走势）；伏笔页加健康环 + 埋设跨度条 + 沉睡预警；
检测页加覆盖率与逐章明细；交互加 Ctrl/⌘+K 命令面板与深浅主题（与阅读器纸张/夜间互不干扰）。
全部图表为手写 SVG，零外部依赖、单文件离线可用。
设计借鉴 QMAI 记忆中心与 awesome-novel-agent 节奏预警，实现为本技能自有轻量版。

用法：
    python tools/visualize.py "<项目根>"           # 生成 看板.html 并自动打开浏览器
    python tools/visualize.py "<项目根>" --no-open # 只生成不打开

退出码：0=生成成功；2=项目根不存在或缺 书稿/ 与 mind/（非阻塞工具，永不因档案缺失报错）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_index import collect_chapters, read_body_chars  # noqa: E402

# ---------------------------------------------------------------- 数据采集

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        # UnicodeDecodeError 已由 errors=replace 兜底；此函数自称「永不因档案缺失报错」，
        # 编码坏点/文件锁同样不能拖垮整块看板（v7.30：此前 GBK 章节会让 collect() 裸崩）
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


def _as_date(s):
    """章节日期 → date；认 `2026-09-22` / `2026/9/22` / `2026年9月22日`，其余（空、模糊）返回 None。
    看板是「永不因档案缺失报错」的工具，日期脏数据只能丢弃，不能抛。"""
    m = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", str(s or ""))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        return None


def _first_int(s):
    """`第12章` / `12` / `12-15` → 12；无数字 → None（用于伏笔埋设章）。"""
    m = re.search(r"(\d+)", str(s or ""))
    return int(m.group(1)) if m else None


def derive(data):
    """派生统计（v7.48 新增·纯只读）：KPI / 字数分布 / 写作热力 / 月度产出 / 类型占比 /
    伏笔健康与沉睡 / 人物出场 / 质量矩阵 / AI 味走势。

    原则：只吃 collect() 已采到的数据，不额外扫盘；任何字段缺失都退化为空列表，
    让 UI 显示空态而不是让整张看板生成失败。
    """
    chs = data.get("chapters") or []
    nos = [c["no"] for c in chs]
    last_no = max(nos) if nos else 0
    counts = [int(c.get("chars") or 0) for c in chs]
    total = sum(counts)

    dated = [(d, c) for d, c in ((_as_date(c.get("date")), c) for c in chs) if d]
    last_date = max((d for d, _ in dated), default=None)
    # 未来日期（预排期/手误）会让断更天数变负数，钳到 0：看板只报"没更新多久"，不报"未来几天"
    idle = max(0, (datetime.now().date() - last_date).days) if last_date else None

    zj = data["scores"]["朱雀"]
    covered = sum(1 for n in nos if n in zj)
    hum = [v["human"] for v in zj.values() if v.get("human") is not None]
    zj_avg = round(sum(hum) / len(hum), 1) if hum else None
    bad = [n for n in nos if n in zj and (zj[n].get("human") or 0) < 80]

    # 章节类型分布（保持首次出现顺序，前端配色才稳定）
    types, tidx = [], {}
    for c in chs:
        t = (c.get("type") or "").strip() or "未标注"
        if t in tidx:
            types[tidx[t]]["n"] += 1
            types[tidx[t]]["chars"] += int(c.get("chars") or 0)
        else:
            tidx[t] = len(types)
            types.append({"name": t, "n": 1, "chars": int(c.get("chars") or 0)})

    # 写作热力（按天聚合）与月度产出
    cal, months, midx = {}, [], {}
    for d, c in dated:
        day = d.isoformat()
        slot = cal.setdefault(day, {"n": 0, "chars": 0})
        slot["n"] += 1
        slot["chars"] += int(c.get("chars") or 0)
        mk = "%04d-%02d" % (d.year, d.month)
        if mk in midx:
            months[midx[mk]]["n"] += 1
            months[midx[mk]]["chars"] += int(c.get("chars") or 0)
        else:
            midx[mk] = len(months)
            months.append({"m": mk, "n": 1, "chars": int(c.get("chars") or 0)})
    months.sort(key=lambda x: x["m"])

    # 伏笔健康 + 沉睡预警（埋设距今 ≥30 章仍是未回收/推进中）
    fs_counts = {"推进中": 0, "未埋": 0, "已回收": 0}
    sleeping = []
    for f in data.get("foreshadow") or []:
        st = f.get("state") or "推进中"
        fs_counts[st] = fs_counts.get(st, 0) + 1
        # 沉睡只针对「推进中」：已回收的已完成，「未埋」尚未开始（属另一类欠账，不按沉睡计）
        if st != "推进中":
            continue
        p = _first_int(f.get("planted"))
        if p and last_no and last_no - p >= 30:
            sleeping.append({"id": f.get("id", ""), "content": f.get("content", ""),
                             "planted": f.get("planted", ""), "gap": last_no - p, "state": st})
    sleeping.sort(key=lambda x: -x["gap"])

    # 人物出场（锚点日志的「人物」列，一个锚点可挂多人，按顿号/逗号拆）
    pmap = {}
    for a in data.get("anchors") or []:
        for name in re.split(r"[、,，/／;；\s（）()]+", a.get("who") or ""):
            name = name.strip()
            if not name or len(name) > 12:
                continue
            rec = pmap.setdefault(name, {"name": name, "n": 0, "first": a["no"], "last": a["no"]})
            rec["n"] += 1
            rec["first"] = min(rec["first"], a["no"])
            rec["last"] = max(rec["last"], a["no"])
    people = sorted(pmap.values(), key=lambda x: (-x["n"], x["name"]))[:15]
    for p in people:
        p["absent"] = max(0, last_no - p["last"])

    # 质量矩阵（字数 × 朱雀分）与 AI 味走势
    matrix = [{"no": c["no"], "t": c.get("title") or "", "x": int(c.get("chars") or 0),
               "y": (zj.get(c["no"]) or {}).get("human"),
               "ai": (zj.get(c["no"]) or {}).get("ai"),
               "aiidx": c.get("aiidx")} for c in chs]
    thin = [c["no"] for c in chs if 0 < int(c.get("chars") or 0) < 2000]

    data["stats"] = {
        "total": total, "avg": round(total / len(chs)) if chs else 0,
        "max": max(counts) if counts else 0, "min": min(counts) if counts else 0,
        "last_no": last_no, "last_date": last_date.isoformat() if last_date else "",
        "idle": idle, "covered": covered,
        "cov_pct": round(covered * 100 / len(chs)) if chs else 0,
        "zj_avg": zj_avg, "bad": bad, "thin": thin, "short": len(thin),
        "undated": len(chs) - len(dated),
    }
    data["types"] = types
    data["cal"] = cal
    data["months"] = months
    data["fs_health"] = {"counts": fs_counts, "sleeping": sleeping}
    data["people"] = people
    data["matrix"] = matrix
    data["aiidx"] = [{"no": c["no"], "v": c["aiidx"]} for c in chs if c.get("aiidx") is not None]
    return data


def collect(root):
    mind = os.path.join(root, "mind")
    root_name = os.path.basename(root.rstrip("\\/")) or root
    data = {"root": root_name,
            # 阅读进度键按「绝对路径哈希」隔离（v7.30：此前只用项目名，不同目录下的
            # 同名项目共享同一 localStorage 键，续读记忆/主题互相污染）
            "rdkey": "kbRead::%s::%s" % (
                root_name, hashlib.md5(os.path.abspath(root).encode("utf-8", "ignore")).hexdigest()[:8]),
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
    return derive(data)

# ---------------------------------------------------------------- HTML 模板

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>看板 · __TITLE__</title>
<style>
:root{--bg:#f4f6fa;--panel:#fff;--panel2:#fafbfd;--line:#e5e9f0;--line2:#eef1f6;--ink:#131a26;--sub:#697689;--acc:#3366ff;--acc2:#7c5cff;--soft:#eef3ff;--ok:#10a05c;--warn:#d98200;--bad:#e03c3c;--shadow:0 1px 2px rgba(15,23,42,.05),0 12px 28px -20px rgba(15,23,42,.35);--r:14px}
html[data-theme="dark"]{--bg:#0c1017;--panel:#141a23;--panel2:#101620;--line:#232b38;--line2:#1b222d;--ink:#e8ecf4;--sub:#8d99ad;--acc:#6d8dff;--acc2:#a78bfa;--soft:#1a2438;--ok:#3ddc84;--warn:#f5b544;--bad:#ff6b6b;--shadow:0 1px 2px rgba(0,0,0,.45),0 16px 34px -22px rgba(0,0,0,.9)}
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.65 "Microsoft YaHei","PingFang SC",system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink);display:flex;min-height:100vh;-webkit-font-smoothing:antialiased}
aside{width:228px;flex-shrink:0;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
.brand{padding:20px 18px 14px;border-bottom:1px solid var(--line2)}
.brand .bt{font-size:16px;font-weight:700;line-height:1.35;word-break:break-all}
.brand .bs{font-size:11px;color:var(--sub);margin-top:5px}
nav{flex:1;overflow:auto;padding:10px}
nav a{display:flex;align-items:center;gap:8px;padding:8px 11px;border-radius:9px;color:var(--ink);text-decoration:none;margin:1px 0;font-size:13.5px;position:relative}
nav a:hover{background:var(--soft)}
nav a.on{background:var(--soft);color:var(--acc);font-weight:600}
nav a.on::before{content:"";position:absolute;left:0;top:50%;transform:translateY(-50%);width:3px;height:15px;border-radius:2px;background:var(--acc)}
nav a .n{margin-left:auto;font-size:11px;color:var(--sub);background:var(--line2);border-radius:9px;padding:0 7px;line-height:17px;font-variant-numeric:tabular-nums}
nav a.on .n{background:var(--panel);color:var(--acc)}
.aside-foot{padding:10px;border-top:1px solid var(--line2);display:flex;gap:6px}
.shell{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;padding:11px 26px;background:var(--bg);border-bottom:1px solid var(--line)}
.crumb{font-size:15px;font-weight:700}
.crumb span{color:var(--sub);font-weight:400;font-size:12px;margin-left:8px}
.tools{margin-left:auto;display:flex;gap:8px;align-items:center}
main{flex:1;padding:22px 26px 40px;max-width:1180px;width:100%}
section{display:none}
section.on{display:block;animation:fade .22s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
h2{font-size:18px;margin-bottom:14px}
h2 small{font-size:12px;color:var(--sub);font-weight:400;margin-left:8px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin-bottom:14px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;box-shadow:var(--shadow)}
.kpi .lab{font-size:11.5px;color:var(--sub)}
.kpi .val{font-size:25px;font-weight:700;line-height:1.3;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.kpi .val small{font-size:12px;font-weight:500;color:var(--sub);margin-left:2px}
.kpi .sub{font-size:11.5px;color:var(--sub);margin-top:1px}
.kpi.acc .val{color:var(--acc)}.kpi.ok .val{color:var(--ok)}.kpi.warn .val{color:var(--warn)}.kpi.bad .val{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow)}
.card h3{font-size:14.5px;margin-bottom:10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.card h3 .hint{margin-left:auto;font-size:11.5px;color:var(--sub);font-weight:400}
.two{display:grid;grid-template-columns:1.55fr 1fr;gap:12px;align-items:start;margin-bottom:12px}
.two>*{margin-bottom:0}
.badge{display:inline-block;font-size:11px;border-radius:9px;padding:1px 9px;background:var(--line2);color:var(--sub);vertical-align:1px}
.badge.t{background:var(--soft);color:var(--acc)}.badge.g{background:rgba(16,160,92,.13);color:var(--ok)}.badge.y{background:rgba(217,130,0,.14);color:var(--warn)}.badge.r{background:rgba(224,60,60,.13);color:var(--bad)}.badge.p{background:rgba(124,92,255,.14);color:var(--acc2)}
.muted{color:var(--sub);font-size:12px}
.kv{margin:3px 0}.kv .k{color:var(--sub);margin-right:6px;white-space:nowrap}
.warnbox{border-left:3px solid var(--warn);background:rgba(217,130,0,.07);border-radius:10px;padding:11px 14px;margin-bottom:14px;font-size:13px}
.warnbox .wt{font-weight:600;color:var(--warn);margin-bottom:3px;font-size:12.5px}
.warnbox .li{font-size:12.5px;margin:2px 0;color:var(--ink)}
.empty{color:var(--sub);text-align:center;padding:34px 0;font-size:13px}
input,select{border:1px solid var(--line);border-radius:9px;padding:7px 11px;font-size:13px;background:var(--panel);color:var(--ink);margin:0 8px 12px 0;outline:none;font-family:inherit}
input:focus,select:focus{border-color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line2);padding:8px 10px;text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:600;background:var(--panel2);white-space:nowrap;font-size:12px}
tr:hover td{background:var(--panel2)}
.snap{border-left:3px solid var(--acc)}
.anchor{margin:5px 0;padding-left:10px;border-left:2px solid var(--line)}
.tl{border-left:2px solid var(--line);margin-left:8px;padding-left:20px}
.tl .item{position:relative;padding-bottom:14px}
.tl .item::before{content:"";position:absolute;left:-26px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--acc);border:2px solid var(--panel);box-shadow:0 0 0 1px var(--line)}
pre.raw{white-space:pre-wrap;word-break:break-word;font:12px/1.7 Consolas,monospace;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px;max-height:70vh;overflow:auto}
.svgbox{width:100%;display:block;overflow:visible}
.vcap{font-size:11.5px;color:var(--sub);margin-top:7px;line-height:1.6}
.dot{display:inline-block;width:8px;height:8px;border-radius:3px;margin-right:4px}
.dot.acc{background:var(--acc)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.ok{background:var(--ok)}
.donutwrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap;justify-content:center}
.legend{font-size:12px;color:var(--sub);display:grid;gap:6px}
.legend b{color:var(--ink);font-variant-numeric:tabular-nums;margin-left:3px}
.tbars{display:grid;gap:10px}
.tb .tbh{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;margin-bottom:4px}
.tbh span:last-child{color:var(--sub);font-size:11.5px;white-space:nowrap}
.tbtrack{height:7px;border-radius:4px;background:var(--line2);overflow:hidden}
.tbtrack i{display:block;height:100%;border-radius:4px}
.pbar{display:grid;gap:9px}
.pb{display:grid;grid-template-columns:76px 1fr 132px;gap:10px;align-items:center;font-size:12.5px}
.pb .pbn{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pb .pbt{position:relative;height:16px;background:var(--line2);border-radius:5px;overflow:hidden}
.pb .pbt i{display:block;height:100%;background:linear-gradient(90deg,var(--acc),var(--acc2));border-radius:5px;opacity:.88}
.pb .pbt em{position:absolute;right:5px;top:0;font-size:10.5px;font-style:normal;line-height:16px}
.pb .pbs{color:var(--sub);font-size:11px;text-align:right;white-space:nowrap}
.cmdk{position:fixed;inset:0;background:rgba(10,14,22,.45);z-index:200;display:none;align-items:flex-start;justify-content:center;padding-top:11vh}
.cmdk.on{display:flex}
.cmdk-box{width:min(600px,92vw);background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:0 24px 60px -20px rgba(0,0,0,.55);overflow:hidden}
.cmdk-box input{width:100%;border:0;border-bottom:1px solid var(--line2);background:transparent;color:var(--ink);padding:15px 18px;font-size:14.5px;outline:none;margin:0;border-radius:0}
.cmdk-list{max-height:52vh;overflow:auto;padding:6px}
.cmdk-item{padding:9px 12px;border-radius:9px;cursor:pointer;display:flex;align-items:center;gap:9px;font-size:13px}
.cmdk-item:hover,.cmdk-item.sel{background:var(--soft)}
.cmdk-item .no{font-size:11px;color:var(--sub);background:var(--line2);border-radius:6px;padding:0 6px;font-variant-numeric:tabular-nums}
.cmdk-item .tp{margin-left:auto;font-size:11px;color:var(--sub)}
.kbd{font-size:10.5px;border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 5px;color:var(--sub);font-family:Consolas,monospace}
.btn{border:1px solid var(--line);border-radius:9px;background:var(--panel);padding:6px 11px;font-size:12.5px;cursor:pointer;color:var(--ink);white-space:nowrap;font-family:inherit;transition:border-color .15s,color .15s}
.btn:hover{border-color:var(--acc);color:var(--acc)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;padding:10px 20px;font-size:14px}
.btn.primary:hover{filter:brightness(1.07);color:#fff}
.btn.ghost{background:transparent}
#rdProg{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--acc),var(--acc2));z-index:150;width:0}
.rdbar{background:var(--bg);padding:0 0 10px;border-bottom:1px solid var(--line);margin-bottom:14px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.rdbar select{max-width:320px;margin:0}
.rdbar .sp{flex:1}
.rdwrap{max-width:820px;margin:0 auto}
.rdtitle{font-size:24px;font-weight:700;text-align:center;margin:8px 0 4px;font-family:Georgia,"Noto Serif SC","Source Han Serif SC",SimSun,serif}
.rdmeta{color:var(--sub);font-size:12px;text-align:center;margin:2px 0 22px}
.rdbody{font-family:Georgia,"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,serif;font-size:19px;line-height:1.95;letter-spacing:.015em;border-radius:12px;padding:26px 32px 22px;border:1px solid var(--line)}
.rdbody p{text-indent:2em;margin:0 0 .35em;min-height:1em}
.rddata[data-thm="paper"] .rdbody{background:#f6f1e5;border-color:#e7ddc6;color:#4a3f2f}
.rddata[data-thm="night"] .rdbody{background:#181a1f;border-color:#262932;color:#c6cbd2}
.rddata[data-thm="night"] .rdtitle{color:#e8eaee}
.rddata[data-thm="night"] .rdmeta{color:#8b919e}
.rddata[data-thm="plain"] .rdbody{background:var(--panel);color:var(--ink)}
.rdfoot{display:flex;gap:10px;margin:18px 0 8px}
.rdfoot button{flex:1;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--panel);font-size:14px;cursor:pointer;color:var(--ink)}
.rdfoot button:hover:not(:disabled){border-color:var(--acc);color:var(--acc)}
.rdfoot button:disabled{opacity:.4;cursor:default}
mark{background:#ffe9a8;color:#3a2f10;padding:0 1px;border-radius:2px}
.flashp{animation:rdflash 2.4s ease-out}
@keyframes rdflash{0%{background:#fff0b8}100%{background:transparent}}
.rdres{margin:10px 0 4px}
.rdres .card{padding:10px 14px;cursor:pointer;margin-bottom:8px;box-shadow:none}
.rdres .card:hover{border-color:var(--acc)}
footer{color:var(--sub);font-size:11px;margin-top:26px;line-height:1.7}
@media(max-width:820px){body{display:block}aside{width:auto;height:auto;position:sticky;top:0;z-index:30;flex-direction:row;align-items:center;border-right:0;border-bottom:1px solid var(--line);overflow-x:auto;padding:8px 10px}.brand{display:none}nav{display:flex;gap:2px;padding:0;flex:1;overflow:visible}nav a{white-space:nowrap;padding:7px 10px}nav a.on::before{display:none}nav a .n{display:none}.aside-foot{display:none}.topbar{display:none}main{padding:14px 12px 32px}.kpi .val{font-size:22px}.rdbody{padding:20px 16px}.rdtitle{font-size:21px}.rdbar select{max-width:170px}.pb{grid-template-columns:66px 1fr}.pb .pbs{display:none}}
</style></head><body>
<div id="rdProg"></div>
<aside>
  <div class="brand"><div class="bt" id="bkTitle"></div><div class="bs" id="bkSub"></div></div>
  <nav id="nav"></nav>
  <div class="aside-foot"><button class="btn ghost" id="thmBtn2" onclick="toggleTheme()">深色模式</button></div>
</aside>
<div class="shell">
  <header class="topbar">
    <div class="crumb"><span id="curName">总览</span><span id="curMeta"></span></div>
    <div class="tools">
      <button class="btn ghost" onclick="cmdkOpen()" title="Ctrl / ⌘ + K"><span class="kbd">Ctrl</span> K 跳转</button>
      <button class="btn ghost" id="thmBtn" onclick="toggleTheme()" title="切换深色 / 浅色">深色</button>
    </div>
  </header>
  <main id="main"></main>
</div>
<div class="cmdk" id="cmdk" onclick="if(event.target===this)cmdkClose()">
  <div class="cmdk-box">
    <input id="cmdkQ" placeholder="跳转章节或分区：输入章号 / 章节名 / 分区名…" oninput="cmdkFilter()" onkeydown="cmdkKey(event)">
    <div class="cmdk-list" id="cmdkList"></div>
  </div>
</div>
<script>
const D = __DATA__;
const esc = s => String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const bold = s => esc(s).replace(/\\*\\*(.+?)\\*\\*/g,"<b>$1</b>");
const H = {"朱雀":90};
const fmt = n => Math.abs(n)>=10000 ? (n/10000).toFixed(n>=100000?0:1)+"万" : String(n);
function badgeCls(v){return v>=H["朱雀"]?"g":v>=80?"y":"r";}
// ---------- 主题（v7.48）：记住上次选择，默认浅色；阅读器的纸张/夜间是独立维度，两者互不干扰 ----------
const TKEY = D.rdkey+"::theme";
function applyTheme(t){
  document.documentElement.dataset.theme=t;
  const b1=document.getElementById("thmBtn"),b2=document.getElementById("thmBtn2");
  if(b1)b1.textContent=t==="dark"?"浅色":"深色";
  if(b2)b2.textContent=t==="dark"?"浅色模式":"深色模式";
}
function toggleTheme(){
  const t=document.documentElement.dataset.theme==="dark"?"light":"dark";
  applyTheme(t);try{localStorage.setItem(TKEY,t)}catch(e){}
}
// ?theme=dark 可固定深色观感（截图/分享用），否则沿用上次选择
try{
  const q=new URLSearchParams(location.search).get("theme");
  applyTheme((q||localStorage.getItem(TKEY))==="dark"?"dark":"light");
}catch(e){applyTheme("light")}
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
  const cs=D.chapters.filter(c=>D.scores["朱雀"][c.no]);
  if(!cs.length)return "<div class='empty'>暂无朱雀检测数据（跑 tools/zhuque_check.py --book 后刷新）</div>";
  const W=780,HH=220,pl=42,pr=56,pt=18,pb=30;
  // 纵轴按数据自适应（分数常年 85+ 时固定在 0-100 会把走势压成一条直线）；90/80 参考线超出范围则不画
  const vals0=cs.map(c=>(D.scores["朱雀"][c.no].human||0));
  const y0=Math.max(0,Math.min(...vals0)-10);
  const y=v=>HH-pb-((v-y0)/((100-y0)||1))*(HH-pt-pb);
  // 章数多时按桶取均值，避免 1000 章把折线糊成实心带
  const step=Math.max(1,Math.ceil(cs.length/160)),arr=[];
  for(let i=0;i<cs.length;i+=step){
    const g=cs.slice(i,i+step);
    const v=g.reduce((s,c)=>s+(D.scores["朱雀"][c.no].human||0),0)/g.length;
    arr.push({no:g[0].no,no2:g[g.length-1].no,v:Math.round(v*10)/10,n:g.length});
  }
  const bw=(W-pl-pr)/Math.max(arr.length-1,1);
  const x=i=>arr.length===1?(pl+pr)/2:pl+i*bw;
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox"><defs><linearGradient id="zjg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--acc)" stop-opacity=".2"/><stop offset="1" stop-color="var(--acc)" stop-opacity="0"/></linearGradient></defs>`;
  [[90,"var(--ok)","90 达标"],[80,"var(--warn)","80 警戒"]].forEach(([lv,c,t])=>{
    if(lv<y0)return;
    s+=`<line x1="${pl}" y1="${y(lv)}" x2="${W-pr}" y2="${y(lv)}" stroke="${c}" stroke-dasharray="4 4" stroke-width="1" opacity=".6"/>`;
    s+=`<text x="${W-pr+6}" y="${y(lv)+3.5}" font-size="9.5" fill="${c}">${t}</text>`;});
  const P=arr.map((p,i)=>[x(i),y(p.v)]);
  if(P.length>1){
    s+=`<path d="M${P.map(p=>p.join(" ")).join("L")}L${P[P.length-1][0]} ${HH-pb}L${P[0][0]} ${HH-pb}Z" fill="url(#zjg)"/>`;
    s+=`<polyline points="${P.map(p=>p.join(",")).join(" ")}" fill="none" stroke="var(--acc)" stroke-width="1.8" stroke-linejoin="round"/>`;}
  arr.forEach((p,i)=>{
    const c=p.v>=90?"var(--ok)":p.v>=80?"var(--warn)":"var(--bad)";
    s+=`<circle cx="${x(i)}" cy="${y(p.v)}" r="${p.n>1?2.6:3.4}" fill="${c}"><title>第${p.no}${p.n>1?"-"+p.no2:""}章 · ${p.v} 分</title></circle>`;
    if(p.n===1)s+=`<text x="${x(i)}" y="${y(p.v)-8}" font-size="9.5" text-anchor="middle" fill="var(--sub)">${p.v}</text>`;});
  const every=Math.max(1,Math.ceil(arr.length/10));
  arr.forEach((p,i)=>{if(i%every)return;
    s+=`<text x="${x(i)}" y="${HH-9}" font-size="9.5" text-anchor="middle" fill="var(--sub)">${p.no}</text>`;});
  return s+`</svg><div class="vcap">朱雀人类分走势（人工占比 · ≥90 达标 / 80-89 警告 / &lt;80 禁止交付）${step>1?` · ${cs.length} 章已按 ${step} 章聚合`:""}</div>`;
}
// ---------- 图表组（v7.48 新增，全部手写 SVG，零外部依赖） ----------
function barsChars(){
  const cs=D.chapters;
  if(!cs.length)return "<div class='empty'>书稿/ 下暂无章节</div>";
  const W=780,HH=250,pl=40,pr=14,pt=16,pb=28;
  const step=Math.max(1,Math.ceil(cs.length/140)),buckets=[];
  for(let i=0;i<cs.length;i+=step){
    const g=cs.slice(i,i+step),n=g.reduce((s,c)=>s+(c.chars||0),0);
    buckets.push({no:g[0].no,no2:g[g.length-1].no,v:Math.round(n/g.length),n:g.length});
  }
  const maxV=Math.max(2200,...buckets.map(b=>b.v))*1.12;
  const bw=(W-pl-pr)/buckets.length;
  const y=v=>HH-pb-(v/maxV)*(HH-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox">`;
  [[2000,"var(--bad)","2000"],[3600,"var(--warn)","3600"]].forEach(([v,c,t])=>{
    if(v>maxV)return;
    s+=`<line x1="${pl}" y1="${y(v).toFixed(1)}" x2="${W-pr}" y2="${y(v).toFixed(1)}" stroke="${c}" stroke-dasharray="3 4" stroke-width="1" opacity=".5"/>`;
    s+=`<text x="${pl-5}" y="${(y(v)+3.3).toFixed(1)}" font-size="8.5" text-anchor="end" fill="${c}">${t}</text>`;});
  buckets.forEach((b,i)=>{
    const ww=Math.max(1.5,bw-(bw>7?3:0.6));
    const col=b.v<2000?"var(--bad)":b.v>3600?"var(--warn)":"var(--acc)";
    const h=Math.max(1.5,HH-pb-y(b.v));
    s+=`<rect x="${(pl+i*bw+(bw-ww)/2).toFixed(1)}" y="${y(b.v).toFixed(1)}" width="${ww.toFixed(1)}" height="${h.toFixed(1)}" rx="${Math.min(3,ww/2).toFixed(1)}" fill="${col}" opacity=".8"><title>第${b.no}${b.n>1?"-"+b.no2:""}章 · 均 ${b.v} 字${b.n>1?"（"+b.n+" 章聚合）":""}</title></rect>`;});
  const every=Math.max(1,Math.ceil(buckets.length/9));
  buckets.forEach((b,i)=>{if(i%every)return;
    s+=`<text x="${(pl+i*bw+bw/2).toFixed(1)}" y="${HH-9}" font-size="9.5" text-anchor="middle" fill="var(--sub)">${b.no}</text>`;});
  return s+`</svg><div class="vcap">每章字数分布（<span class="dot bad"></span>不足 2000 · <span class="dot acc"></span>2000-3600 · <span class="dot warn"></span>超 3600）${step>1?` · ${cs.length} 章按 ${step} 章聚合`:""}</div>`;
}
function donut(){
  const items=[["已回收","var(--ok)"],["推进中","var(--acc)"],["未埋","var(--warn)"]]
    .map(([k,c])=>({k,v:D.fs_health.counts[k]||0,c}));
  const total=items.reduce((s,x)=>s+x.v,0);
  if(!total)return "<div class='empty'>mind/伏笔追踪表.md 无数据</div>";
  const R=52,r=34,cx=64,cy=64;let a=-Math.PI/2;
  let s=`<svg viewBox="0 0 128 128" style="width:128px;height:128px;flex:none">`;
  items.forEach(it=>{
    if(!it.v)return;
    const ang=it.v/total*Math.PI*2,a2=a+ang,large=ang>Math.PI?1:0;
    const p=(rad,t)=>[(cx+rad*Math.cos(t)).toFixed(2),(cy+rad*Math.sin(t)).toFixed(2)];
    const A=p(R,a),B=p(R,a2),C=p(r,a2),E=p(r,a);
    s+=`<path d="M${A} A${R} ${R} 0 ${large} 1 ${B} L${C} A${r} ${r} 0 ${large} 0 ${E} Z" fill="${it.c}" opacity=".9"><title>${it.k} ${it.v}</title></path>`;
    a=a2;});
  s+=`<text x="${cx}" y="${cy-1}" text-anchor="middle" font-size="19" font-weight="700" fill="var(--ink)">${total}</text>`;
  s+=`<text x="${cx}" y="${cy+13}" text-anchor="middle" font-size="9" fill="var(--sub)">条伏笔</text></svg>`;
  return `<div class="donutwrap">${s}<div class="legend">${items.map(i=>`<div><span class="dot" style="background:${i.c}"></span>${i.k}<b>${i.v}</b></div>`).join("")}</div></div>`;
}
function heatCal(){
  const keys=Object.keys(D.cal||{});
  if(!keys.length)return "<div class='empty'>章节日期缺失，无法绘制写作热力（在 mind/章节目录.md 补「日期」列后重跑）</div>";
  const WEEKS=27,CELL=13,GAP=3,LEFT=28,TOP=16;
  const today=new Date();today.setHours(0,0,0,0);
  const start=new Date(today);start.setDate(today.getDate()-(WEEKS*7-1));
  start.setDate(start.getDate()-((start.getDay()+6)%7));
  const days=Math.round((today-start)/864e5)+1,cols=Math.ceil(days/7);
  const W=LEFT+cols*(CELL+GAP),HH=TOP+7*(CELL+GAP)+2;
  const maxN=Math.max(1,...keys.map(k=>D.cal[k].n));
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox" style="max-width:${W}px">`;
  ["一","","三","","五","","日"].forEach((wd,r)=>{if(wd)
    s+=`<text x="${LEFT-7}" y="${TOP+r*(CELL+GAP)+CELL-3.5}" font-size="8.5" text-anchor="end" fill="var(--sub)">${wd}</text>`;});
  let lastM=-1;
  for(let i=0;i<days;i++){
    const d=new Date(start);d.setDate(start.getDate()+i);
    if(d>today)break;
    const k=d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
    const rec=D.cal[k];
    const cx=LEFT+Math.floor(i/7)*(CELL+GAP),cy=TOP+(i%7)*(CELL+GAP);
    s+=`<rect x="${cx}" y="${cy}" width="${CELL}" height="${CELL}" rx="3.5" fill="${rec?"var(--acc)":"var(--line2)"}" opacity="${rec?Math.min(1,.3+.7*(rec.n/maxN)).toFixed(2):"1"}"><title>${k}${rec?` · ${rec.n} 章 / ${rec.chars} 字`:" · 未更新"}</title></rect>`;
    if(d.getDate()===1&&d.getMonth()!==lastM){lastM=d.getMonth();
      s+=`<text x="${cx}" y="${TOP-4}" font-size="8.5" fill="var(--sub)">${d.getMonth()+1}月</text>`;}
  }
  return s+`</svg><div class="vcap">最近 ${WEEKS} 周写作热力（越深=当天章数越多，悬停看当日字数）· 有更新记录 ${keys.length} 天</div>`;
}
function monthBars(){
  const ms=D.months||[];
  if(!ms.length)return "<div class='empty'>章节日期缺失，无法统计月度产出</div>";
  const W=780,HH=190,pl=42,pr=12,pt=18,pb=28;
  const maxV=Math.max(...ms.map(m=>m.chars),1);
  const bw=(W-pl-pr)/ms.length,y=v=>HH-pb-(v/maxV)*(HH-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox">`;
  ms.forEach((m,i)=>{
    const ww=Math.max(6,Math.min(bw*0.6,110)),xx=pl+i*bw+(bw-ww)/2;
    s+=`<rect x="${xx.toFixed(1)}" y="${y(m.chars).toFixed(1)}" width="${ww.toFixed(1)}" height="${Math.max(1.5,HH-pb-y(m.chars)).toFixed(1)}" rx="4" fill="var(--acc2)" opacity=".82"><title>${m.m} · ${m.n} 章 / ${m.chars} 字</title></rect>`;
    s+=`<text x="${(pl+i*bw+bw/2).toFixed(1)}" y="${(y(m.chars)-5).toFixed(1)}" font-size="9" text-anchor="middle" fill="var(--sub)">${fmt(m.chars)}</text>`;
    s+=`<text x="${(pl+i*bw+bw/2).toFixed(1)}" y="${HH-9}" font-size="9" text-anchor="middle" fill="var(--sub)">${m.m.slice(2)}</text>`;});
  const act=ms.filter(m=>m.n>0).length||1;
  return s+`</svg><div class="vcap">月度产出（柱高=当月字数，悬停看章数）· 活跃月均 ${(ms.reduce((a,m)=>a+m.chars,0)/act/10000).toFixed(2)} 万字</div>`;
}
function typeBars(){
  const ts=D.types||[];
  if(!ts.length)return "<div class='empty'>章节目录缺「类型」列，无法统计节奏结构</div>";
  const tot=ts.reduce((s,t)=>s+t.n,0)||1;
  const cols=["var(--acc)","var(--acc2)","var(--ok)","var(--warn)","var(--bad)","#0ea5e9","#ec4899","#14b8a6"];
  return `<div class="tbars">`+ts.map((t,i)=>`<div class="tb"><div class="tbh"><span>${esc(t.name)}</span><span>${t.n} 章 · ${(t.n/tot*100).toFixed(0)}% · ${fmt(t.chars)} 字</span></div><div class="tbtrack"><i style="width:${(t.n/tot*100).toFixed(1)}%;background:${cols[i%cols.length]}"></i></div></div>`).join("")+`</div>`
    +`<div class="vcap">节奏结构：缓冲章占比过高会让读者觉得"水"，主线长期连排则会疲劳。</div>`;
}
function peopleBars(){
  if(!D.people.length)return "<div class='empty'>mind/锚点日志.md 缺「人物」列，无法统计出场</div>";
  const max=Math.max(...D.people.map(p=>p.n));
  return `<div class="pbar">`+D.people.map(p=>`<div class="pb"><div class="pbn">${esc(p.name)}</div><div class="pbt"><i style="width:${(p.n/max*100).toFixed(1)}%"></i><em>${p.n}</em></div><div class="pbs">首${p.first} · 近${p.last}${p.absent>0?" · 缺"+p.absent+"章":""}</div></div>`).join("")+`</div>`
    +`<div class="vcap">主要人物出场频次（按锚点日志计）·「缺N章」=距最新章已缺席的章数，长期缺席需交代去向。</div>`;
}
const intOf=s=>{const m=String(s||"").match(/(\\d+)/);return m?+m[1]:null;};
function fsSpan(){
  const last=D.stats.last_no||1;
  const items=D.foreshadow.map(f=>{
    const p=intOf(f.planted),e=intOf(f.payoff);
    return {id:f.id,state:f.state,p:p,e:e||last};
  }).filter(f=>f.p!=null);
  if(!items.length)return "<div class='empty'>伏笔表缺「埋设」章号</div>";
  const show=items.slice(0,12),rowH=22,pl=8,pr=8,top=8;
  const W=760,HH=top+show.length*rowH+12;
  const X=n=>pl+Math.min(1,Math.max(0,(n-1)/Math.max(1,last-1)))*(W-pl-pr);
  let s=`<svg viewBox="0 0 ${W} ${HH+14}" class="svgbox">`;
  show.forEach((f,i)=>{
    const yy=top+i*rowH+8;
    const col=f.state==="已回收"?"var(--ok)":f.state==="未埋"?"var(--warn)":"var(--acc)";
    const x1=X(f.p),x2=X(f.e),over=f.e>last;
    s+=`<line x1="${x1.toFixed(1)}" y1="${yy}" x2="${x2.toFixed(1)}" y2="${yy}" stroke="${col}" stroke-width="3" stroke-linecap="round" opacity=".5"${over?' stroke-dasharray="5 4"':""}/>`;
    s+=`<circle cx="${x1.toFixed(1)}" cy="${yy}" r="4" fill="${col}"><title>${esc(f.id)} 埋于第${f.p}章</title></circle>`;
    s+=`<circle cx="${x2.toFixed(1)}" cy="${yy}" r="3" fill="${col}" opacity=".45"><title>${esc(f.id)} 收于第${f.e}章</title></circle>`;
    s+=`<text x="${x1.toFixed(1)}" y="${yy-7}" font-size="8.5" fill="var(--sub)">${esc(f.id)}</text>`;
  });
  s+=`<line x1="${pl}" y1="${HH-2}" x2="${W-pr}" y2="${HH-2}" stroke="var(--line)" stroke-width="1"/>`;
  s+=`<text x="${pl}" y="${HH+11}" font-size="8.5" fill="var(--sub)">第1章</text>`;
  s+=`<text x="${W-pr}" y="${HH+11}" font-size="8.5" text-anchor="end" fill="var(--sub)">第${last}章</text>`;
  return s+`</svg><div class="vcap">伏笔跨度：左圆点=埋设章，右圆点=预计/实际回收章（全轴 1-${last} 章）· 线越长，读者等得越久。</div>`;
}
function scatter(){
  const pts=(D.matrix||[]).filter(m=>m.y!=null&&m.x>0);
  if(!pts.length)return "<div class='empty'>暂无「字数×朱雀分」数据，跑一次朱雀检测后重试</div>";
  const W=780,HH=300,pl=42,pr=18,pt=18,pb=32;
  const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);
  const x0=Math.min(...xs)*0.92,x1=Math.max(...xs)*1.06||1;
  const y0=Math.max(0,Math.min(...ys)-6),y1=100;
  const X=v=>pl+(v-x0)/((x1-x0)||1)*(W-pl-pr);
  const Y=v=>HH-pb-(v-y0)/((y1-y0)||1)*(HH-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox">`;
  [[90,"var(--ok)","90 达标"],[80,"var(--warn)","80 警戒"]].forEach(([v,c,t])=>{
    s+=`<line x1="${pl}" y1="${Y(v).toFixed(1)}" x2="${W-pr}" y2="${Y(v).toFixed(1)}" stroke="${c}" stroke-dasharray="4 4" opacity=".5"/><text x="${pl+3}" y="${(Y(v)-4).toFixed(1)}" font-size="9" fill="${c}">${t}</text>`;});
  const x2000=X(2000);
  if(x2000>pl&&x2000<W-pr)s+=`<line x1="${x2000.toFixed(1)}" y1="${pt}" x2="${x2000.toFixed(1)}" y2="${HH-pb}" stroke="var(--bad)" stroke-dasharray="3 4" opacity=".45"/><text x="${(x2000+4).toFixed(1)}" y="${HH-pb-5}" font-size="9" fill="var(--bad)">2000 字</text>`;
  pts.forEach(p=>{const c=p.y>=90?"var(--ok)":p.y>=80?"var(--warn)":"var(--bad)";
    s+=`<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4.5" fill="${c}" opacity=".7" stroke="var(--panel)" stroke-width="1"><title>第${p.no}章 ${p.t} · ${p.x} 字 / ${p.y} 分</title></circle>`;});
  s+=`<text x="${W-pr}" y="${HH-8}" font-size="9" text-anchor="end" fill="var(--sub)">字数 →</text>`;
  return s+`</svg><div class="vcap">质量矩阵：横轴字数、纵轴朱雀分。右上=又长又好（理想区），左下=又短又危险（优先返工）。</div>`;
}
function aiTrend(){
  const arr=D.aiidx||[];
  if(!arr.length)return "<div class='empty'>章节目录「检查」列没有 AI味 x/10 记录（跑 check_chapter.py 后自动写入）</div>";
  const W=780,HH=180,pl=32,pr=16,pt=16,pb=28;
  const n=arr.length,bw=(W-pl-pr)/Math.max(n-1,1),Y=v=>HH-pb-(v/10)*(HH-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${HH}" class="svgbox">`;
  [[4,"var(--warn)"],[6,"var(--bad)"]].forEach(([v,c])=>{
    s+=`<line x1="${pl}" y1="${Y(v).toFixed(1)}" x2="${W-pr}" y2="${Y(v).toFixed(1)}" stroke="${c}" stroke-dasharray="4 4" opacity=".55"/><text x="${pl-4}" y="${(Y(v)+3.3).toFixed(1)}" font-size="8.5" text-anchor="end" fill="${c}">${v}</text>`;});
  const P=arr.map((a,i)=>[n===1?(pl+pr)/2:pl+i*bw,Y(a.v)]);
  s+=`<polyline points="${P.map(p=>p.join(",")).join(" ")}" fill="none" stroke="var(--acc2)" stroke-width="1.8" stroke-linejoin="round"/>`;
  arr.forEach((a,i)=>{const c=a.v>=6?"var(--bad)":a.v>=4?"var(--warn)":"var(--ok)";
    s+=`<circle cx="${P[i][0].toFixed(1)}" cy="${P[i][1].toFixed(1)}" r="3" fill="${c}"><title>第${a.no}章 · AI味 ${a.v}/10</title></circle>`;});
  return s+`</svg><div class="vcap">AI 味指数（0-10，越低越像人写；≥4 该回炉，≥6 高危）</div>`;
}
const anchorsOf=no=>D.anchors.filter(a=>a.no===no);
const tlOf=no=>D.timeline.find(t=>t.no===no);
// ---------- 正文阅读器（v7.22）：续读记忆/翻章/主题/字号/全文搜索 ----------
const THEME_NAMES={paper:"纸张",night:"夜间",plain:"白底"};
const RDKEY=D.rdkey;
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
   const st=D.stats,chs=D.chapters,last=chs.length?chs[chs.length-1]:null;
   const zk=Object.keys(D.scores["朱雀"]);
   const lz=zk.length?D.scores["朱雀"][zk.sort((a,b)=>a-b)[zk.length-1]].human:null;
   const zc=lz==null?"":(lz>=90?"ok":lz>=80?"warn":"bad");
   const warns=[];
   D.rhythm_warn.forEach(t=>warns.push("节奏 · "+t));
   D.fs_health.sleeping.slice(0,4).forEach(f=>warns.push(`伏笔 ${f.id}「${f.content}」已埋 ${f.gap} 章未回收（${f.planted}）`));
   if(st.short)warns.push(`${st.short} 章不足 2000 字：第 ${st.thin.slice(0,8).join("、")}${st.thin.length>8?"…":""} 章`);
   if(st.idle!=null&&st.idle>=7)warns.push(`已 ${st.idle} 天没更新（最后一章 ${st.last_date}）`);
   if(chs.length&&st.covered<chs.length)warns.push(`检测覆盖 ${st.covered}/${chs.length} 章，还有 ${chs.length-st.covered} 章没跑朱雀`);
   if(st.undated)warns.push(`章节目录有 ${st.undated} 章缺日期，写作热力与月度产出会漏算`);
   const cur=RD.cur!=null&&chs.some(c=>c.no===RD.cur)?chs.find(c=>c.no===RD.cur):chs[0];
   return `<div class="kpis">
    <div class="kpi acc"><div class="lab">章节</div><div class="val">${chs.length}</div><div class="sub">${last?"最新 第"+last.no+"章":"尚无章节"}</div></div>
    <div class="kpi"><div class="lab">总字数</div><div class="val">${fmt(st.total)}</div><div class="sub">均 ${st.avg} 字/章</div></div>
    <div class="kpi ${zc}"><div class="lab">朱雀均分</div><div class="val">${st.zj_avg==null?"—":st.zj_avg}</div><div class="sub">覆盖 ${st.covered}/${chs.length} 章</div></div>
    <div class="kpi"><div class="lab">伏笔</div><div class="val">${D.fs_health.counts["推进中"]||0}<small>推进中</small></div><div class="sub">未埋 ${D.fs_health.counts["未埋"]||0} · 已回收 ${D.fs_health.counts["已回收"]||0}</div></div>
    <div class="kpi ${st.idle!=null&&st.idle>=3?"warn":""}"><div class="lab">距上次更新</div><div class="val">${st.idle==null?"—":(st.idle===0?"今天":st.idle+"<small>天</small>")}</div><div class="sub">${st.last_date||"无日期记录"}</div></div>
    <div class="kpi ${st.bad.length?"bad":"ok"}"><div class="lab">低于 80 分</div><div class="val">${st.bad.length}<small>章</small></div><div class="sub">${st.bad.length?"第 "+st.bad.slice(0,4).join("、")+(st.bad.length>4?"…":"")+" 章":"暂无危险章"}</div></div>
   </div>`
   +(chs.length?`<div class="card" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
     <div style="flex:1;min-width:200px"><h3 style="margin:0">${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?"📖 继续阅读":"📖 开始阅读"}</h3>
     <div class="muted">${esc(cur?("第"+cur.no+"章 "+cur.title):"")} · ${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?"记住了上次的章节与位置":"支持翻章 / 字号 / 三主题 / 全文搜索"} · <span class="kbd">Ctrl</span>+<span class="kbd">K</span> 全局跳转</div></div>
     <button class="btn primary" onclick="rdCont()">${RD.cur!=null&&chs.some(c=>c.no===RD.cur)?"继续阅读 →":"开始阅读 →"}</button></div>`:"")
   +(warns.length?`<div class="warnbox"><div class="wt">待处理 ${warns.length} 项</div>${warns.slice(0,7).map(w=>`<div class="li">· ${esc(w)}</div>`).join("")}${warns.length>7?`<div class="li" style="color:var(--sub)">· 另有 ${warns.length-7} 项，见对应分区</div>`:""}</div>`:"")
   +`<div class="two"><div class="card"><h3>每章字数<span class="hint">${chs.length?st.min+"–"+st.max+" 字":"暂无章节"}</span></h3>${barsChars()}</div><div class="card"><h3>伏笔健康</h3>${donut()}</div></div>`
   +`<div class="card"><h3>朱雀人类分走势<span class="hint">${st.zj_avg==null?"暂无检测":"均分 "+st.zj_avg}</span></h3>${chart()}</div>`
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
   const c=D.fs_health.counts,tot=(c["推进中"]||0)+(c["未埋"]||0)+(c["已回收"]||0)||1;
   const sl=D.fs_health.sleeping;
   return `<div class="two" style="grid-template-columns:300px 1fr">
     <div class="card"><h3>健康度<span class="hint">回收率 ${Math.round((c["已回收"]||0)/tot*100)}%</span></h3>${donut()}</div>
     <div class="card"><h3>埋设跨度</h3>${fsSpan()}</div></div>`
   +(sl.length?`<div class="warnbox"><div class="wt">沉睡伏笔 ${sl.length} 条（埋设 ≥30 章仍未回收）</div>${sl.map(f=>`<div class="li">· ${esc(f.id)}「${esc(f.content)}」${esc(f.planted)} 埋，已过 ${f.gap} 章</div>`).join("")}</div>`:"")
   +`<div class="card"><table><tr><th>编号</th><th>内容</th><th>埋设</th><th>预计回收</th><th>Tier</th><th>状态</th></tr>`
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
 {id:"anl",name:"写作分析",f:()=>{
   return `<div class="card"><h3>写作热力<span class="hint">最近 27 周</span></h3>${heatCal()}</div>`
   +`<div class="card"><h3>月度产出</h3>${monthBars()}</div>`
   +`<div class="two"><div class="card"><h3>质量矩阵<span class="hint">字数 × 朱雀分</span></h3>${scatter()}</div><div class="card"><h3>节奏结构</h3>${typeBars()}</div></div>`
   +`<div class="two"><div class="card"><h3>主要人物出场</h3>${peopleBars()}</div><div class="card"><h3>AI 味指数</h3>${aiTrend()}</div></div>`;
 }},
 {id:"det",name:"检测报告",f:()=>{
   const zj=D.files.find(f=>f.name==="朱雀检测报告.md"),mo=D.files.find(f=>f.name==="墨尺检测报告.md");
   const st=D.stats,tail=150;
   const det=D.chapters.filter(c=>D.scores["朱雀"][c.no]||D.scores["墨尺"][c.no]);
   const shown=det.slice(-tail);
   const rows=shown.map(c=>{
     const s=D.scores["朱雀"][c.no],m=D.scores["墨尺"][c.no];
     const v=s?s.human:(m?m.human:null);
     return `<tr><td>第${c.no}章</td><td>${esc(c.title)}</td><td>${c.chars||0}</td><td><b>${s?s.human:"—"}</b></td><td>${s&&s.ai!=null?s.ai+"%":"—"}</td><td>${m?m.human:"—"}</td><td>${v==null?"—":`<span class="badge ${badgeCls(v)}">${v>=90?"达标":v>=80?"警告":"禁止交付"}</span>`}</td></tr>`;}).join("");
   return `<div class="kpis">
      <div class="kpi ${D.chapters.length&&st.covered===D.chapters.length?"ok":"warn"}"><div class="lab">朱雀覆盖</div><div class="val">${st.cov_pct}<small>%</small></div><div class="sub">${st.covered}/${D.chapters.length} 章</div></div>
      <div class="kpi ${st.bad.length?"bad":"ok"}"><div class="lab">低于 80 分</div><div class="val">${st.bad.length}<small>章</small></div><div class="sub">需返工</div></div>
      <div class="kpi"><div class="lab">朱雀均分</div><div class="val">${st.zj_avg==null?"—":st.zj_avg}</div><div class="sub">已测章均值</div></div>
    </div>`
   +`<div class="card"><h3>分数走势</h3>${chart()}</div>`
   +(rows?`<div class="card"><h3>逐章检测明细<span class="hint">${det.length>tail?"仅显示最近 "+tail+" 章":"共 "+det.length+" 章"}</span></h3><table><tr><th>章</th><th>标题</th><th>字数</th><th>朱雀人类分</th><th>AI%</th><th>墨尺</th><th>结论</th></tr>${rows}</table></div>`:"")
   +(zj?`<div class="card"><h3>朱雀检测报告原文</h3><pre class="raw">${esc(zj.text)}</pre></div>`:"")
   +(mo?`<div class="card"><h3>墨尺检测报告原文</h3><pre class="raw">${esc(mo.text)}</pre></div>`:"")
   +(!zj&&!mo?"<div class='empty'>暂无检测报告</div>":"");
 }},
 {id:"arch",name:"档案库",n:D.files.length,f:()=>{
   return `<select id="archSel" onchange="archShow(this.value)">${D.files.map((f,i)=>`<option value="${i}">${esc(f.name)}</option>`).join("")}</select><div id="archView"></div>`;
 }}
];
const RD_I=SECTIONS.findIndex(s=>s.id==="rd");
// ---------- 命令面板（v7.48）：Ctrl/⌘+K 跳章节或分区，↑↓ 选择 + 回车 ----------
let CMDK_HIT=[],CMDK_SEL=0;
function cmdkAll(){
  const out=SECTIONS.map((s,i)=>({k:"区",label:s.name,sub:"分区",g:()=>go(i)}));
  D.chapters.forEach(c=>out.push({k:"章",label:`第${c.no}章 ${c.title}`,
    sub:(c.type?c.type+" · ":"")+(c.chars||0)+"字",g:()=>rdJump(c.no)}));
  return out;
}
function cmdkOpen(){
  document.getElementById("cmdk").classList.add("on");
  const q=document.getElementById("cmdkQ");q.value="";cmdkFilter();q.focus();
}
function cmdkClose(){document.getElementById("cmdk").classList.remove("on");}
function cmdkFilter(){
  const q=(document.getElementById("cmdkQ").value||"").trim().toLowerCase();
  if(!CMDK_HIT.length)CMDK_HIT=cmdkAll();
  const hit=CMDK_HIT.filter(x=>!q||x.label.toLowerCase().includes(q)).slice(0,60);
  window.__hit=hit;CMDK_SEL=0;
  document.getElementById("cmdkList").innerHTML=hit.length
    ?hit.map((x,i)=>`<div class="cmdk-item${i===0?" sel":""}" onclick="cmdkPick(${i})"><span class="no">${x.k}</span><span>${esc(x.label)}</span><span class="tp">${esc(x.sub)}</span></div>`).join("")
    :`<div class="empty" style="padding:22px 0">没有匹配项</div>`;
}
function cmdkPick(i){const hit=window.__hit||[];if(!hit[i])return;cmdkClose();hit[i].g();}
function cmdkKey(e){
  const hit=window.__hit||[];
  if(e.key==="Escape"){cmdkClose();return}
  if(!hit.length)return;
  if(e.key==="ArrowDown"||e.key==="ArrowUp"){
    e.preventDefault();
    CMDK_SEL=(CMDK_SEL+(e.key==="ArrowDown"?1:hit.length-1))%hit.length;
    document.querySelectorAll(".cmdk-item").forEach((el,j)=>el.classList.toggle("sel",j===CMDK_SEL));
    const sel=document.querySelector(".cmdk-item.sel");if(sel)sel.scrollIntoView({block:"nearest"});
  }else if(e.key==="Enter"){e.preventDefault();cmdkPick(CMDK_SEL);}
}
document.addEventListener("keydown",e=>{
  if((e.ctrlKey||e.metaKey)&&(e.key==="k"||e.key==="K")){e.preventDefault();cmdkOpen();}
  else if(e.key==="Escape"&&document.getElementById("cmdk").classList.contains("on"))cmdkClose();
});
function render(){
  document.getElementById("bkTitle").textContent=D.root;
  document.getElementById("bkSub").textContent="生成于 "+D.generated+" · 网络小说创作技能 __SKILL_VER__";
  document.getElementById("nav").innerHTML=SECTIONS.map((s,i)=>`<a href="#${s.id}" data-i="${i}" onclick="go(${i});return false"><span>${s.name}</span>${s.n!=null?`<span class="n">${s.n}</span>`:""}</a>`).join("");
  document.getElementById("main").innerHTML=SECTIONS.map((s,i)=>`<section id="sec${i}" class="section"><h2>${s.name}</h2>${s.f()}</section>`).join("")+"<footer>本看板由 tools/visualize.py 生成 · 数据源：书稿/ + mind/ · 改动后重跑即可刷新 · 阅读进度与主题存在本机浏览器（localStorage），换电脑不跟随</footer>";
  archShow(0);
  if(D.chapters.length){
    RD.cur=D.chapters.some(c=>c.no===RD.cur)?RD.cur:D.chapters[0].no;
    openCh(RD.cur,null,false);
    const tb=document.getElementById("rdThmBtn");if(tb)tb.textContent="主题·"+(THEME_NAMES[RD.thm]||"纸张");
    const v=document.getElementById("rdView");if(v)v.dataset.thm=RD.thm;}
  const h=location.hash.slice(1),idx=SECTIONS.findIndex(s=>s.id===h);
  go(idx>0?idx:0,true);
  if(idx===RD_I&&idx>0)openCh(RD.cur,null,true);
}
function go(i,noHash){
  if(!SECTIONS[i])i=0;
  document.querySelectorAll("nav a").forEach((a,j)=>a.classList.toggle("on",i===j));
  document.querySelectorAll(".section").forEach((s,j)=>s.classList.toggle("on",i===j));
  const cn=document.getElementById("curName");if(cn)cn.textContent=SECTIONS[i].name;
  const cm=document.getElementById("curMeta");
  if(cm)cm.textContent=D.stats&&D.stats.total?"· "+fmt(D.stats.total)+" 字 · 更新至第"+D.stats.last_no+"章":"";
  if(!noHash){try{history.replaceState(null,"","#"+SECTIONS[i].id)}catch(e){}}
  RD_ON=SECTIONS[i].id==="rd";
  if(RD_ON&&D.chapters.length)window.scrollTo(0,(document.body.scrollHeight-innerHeight)*(RD.pct||0));
  else window.scrollTo(0,0);
}
function pcFilter(q){q=q.toLowerCase();document.querySelectorAll(".pc").forEach(c=>c.style.display=c.dataset.s.toLowerCase().includes(q)?"":"none");}
function anFilter(){const c=document.getElementById("anCat").value,q=(document.getElementById("anQ").value||"").toLowerCase();
  document.querySelectorAll(".an").forEach(x=>x.style.display=(x.dataset.c===c||!c)&&x.dataset.s.toLowerCase().includes(q)?"":"none");}
function archShow(i){const f=D.files[i];if(!f)return;document.getElementById("archView").innerHTML=`<div class="card">${md(f.text)}</div>`;}
render();
</script></body></html>"""

# ---------------------------------------------------------------- 主流程

def skill_version():
    """从技能包 SKILL.md 头部读版本号，读不到回退 v7.27。"""
    fallback = "v7.27"
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
        # as_uri() 自动产出 file:/// 三斜杠 + 百分号编码（v7.30：路径含 #/?/& 时
        # 裸拼 "file://"+路径会被浏览器错误解析）
        webbrowser.open(Path(out).resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
