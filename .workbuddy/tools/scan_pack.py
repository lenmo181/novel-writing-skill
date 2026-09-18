# -*- coding: utf-8 -*-
"""技能包上架前体检：体积/结构/敏感信息/引用完整性"""
import os, re, sys, json

ROOT = r"C:\Users\lenmo\Desktop\网络小说创作技能"
SKIP_DIRS = {".workbuddy", "__pycache__", ".git"}

files = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in SKIP_DIRS]
    for fn in fns:
        p = os.path.join(dp, fn)
        files.append((p, os.path.getsize(p)))

total = sum(s for _, s in files)
print("=== 体积 ===")
print("总大小: %.2f MB (%d bytes)  | 文件数: %d" % (total / 1024 / 1024, total, len(files)))
print("ZIP 上限 3MB -> %s" % ("超限！" if total > 3 * 1024 * 1024 else "OK"))

print("\n=== 顶层结构 ===")
for name in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, name)
    if os.path.isdir(p):
        n = sum(1 for dp, _, fs in os.walk(p) for f in fs if all(x not in SKIP_DIRS for x in dp.split(os.sep)))
        sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(p) for f in fs)
        print("  [DIR ] %-22s %2d files  %6.1f KB" % (name + "/", n, sz / 1024))
    else:
        print("  [FILE] %-22s            %6.1f KB" % (name, os.path.getsize(p) / 1024))

print("\n=== 最大 12 个文件 ===")
for p, s in sorted(files, key=lambda x: -x[1])[:12]:
    print("  %8.1f KB  %s" % (s / 1024, p.replace(ROOT, "")[1:]))

# 敏感信息扫描
PATS = [
    ("个人绝对路径(lenmo)", re.compile(r"[Cc]:[\\/]Users[\\/]lenmo")),
    ("其他绝对路径", re.compile(r"[Cc]:[\\/]Users[\\/](?!lenmo)[A-Za-z0-9_.\-]+")),
    ("OpenAI风格Key", re.compile(r"sk-[A-Za-z0-9\-_]{16,}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("Bearer/Cookie", re.compile(r"(?i)(bearer\s+[A-Za-z0-9\-_.]{20,}|cookie\s*[:=]\s*\S{20,})")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("疑似密码字段", re.compile(r"(?i)(password|passwd|secret|api[_-]?key)\s*[:=]\s*[\"'][^\"'\s]{6,}")),
]
print("\n=== 敏感信息扫描 ===")
hits = {}
for p, _ in files:
    if not p.lower().endswith((".md", ".py", ".txt", ".json", ".yaml", ".yml", ".html", ".js", ".ts", ".sh")):
        continue
    try:
        txt = open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for label, pat in PATS:
        for m in pat.finditer(txt):
            hits.setdefault(label, []).append((p.replace(ROOT, "")[1:], m.group(0)[:80]))
for label, lst in hits.items():
    print("  [%s] %d 处" % (label, len(lst)))
    for f, g in lst[:6]:
        print("      %s  ->  %s" % (f, g))

print("\n=== 相对引用检查（@references / tools） ===")
md = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
refs = sorted(set(re.findall(r"references/[^\s`\"')\]]+\.md", md)))
tos = sorted(set(re.findall(r"tools/[^\s`\"')\]]+\.py", md)))
miss_ref = [r for r in refs if not os.path.exists(os.path.join(ROOT, r.replace("/", os.sep)))]
miss_tool = [t for t in tos if not os.path.exists(os.path.join(ROOT, t.replace("/", os.sep)))]
print("  references 引用 %d 个，缺失 %d 个: %s" % (len(refs), len(miss_ref), miss_ref or "-"))
print("  tools 引用 %d 个，缺失 %d 个: %s" % (len(tos), len(miss_tool), miss_tool or "-"))

# frontmatter 检查
print("\n=== frontmatter ===")
if md.startswith("---"):
    fm = md.split("---", 2)[1]
    present = re.findall(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:", fm, re.M)
    print("  现有字段: %s" % present)
    need = ["name", "display_name", "display_name_en", "description", "description_zh", "description_en", "category", "version", "author"]
    print("  平台必填/推荐缺: %s" % [x for x in need if x not in present])
    for k in ("description", "description_zh"):
        m = re.search(r"^%s\s*:\s*(.*)$" % k, fm, re.M)
        if m:
            print("  %s 长度 = %d 字符" % (k, len(m.group(1))))
