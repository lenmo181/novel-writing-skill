# -*- coding: utf-8 -*-
"""
技能上架包构建器
- 从源目录构建符合 WorkBuddy 开放平台规范的 ZIP
- 源目录零改动：所有改造只在 .workbuddy/tmp/stage 里做
"""
import os, re, shutil, zipfile, subprocess, sys

ROOT = r"C:\Users\lenmo\Desktop\网络小说创作技能"
SKILL_NAME = "网络小说创作技能"
VER = "7.25.0"
STAGE_ROOT = os.path.join(ROOT, ".workbuddy", "tmp", "stage")
STAGE = os.path.join(STAGE_ROOT, SKILL_NAME)
DIST = os.path.join(ROOT, "dist")
ZIP_PATH = os.path.join(DIST, "%s_v%s_market.zip" % (SKILL_NAME, VER))

EXCLUDE_DIRS = {".git", ".workbuddy", ".v2c", ".video_agent", "__pycache__",
                ".idea", ".vscode", "dist", "out", "tests"}
EXCLUDE_FILES = {".gitignore", "Thumbs.db", ".DS_Store"}
TEXT_EXT = {".md", ".py", ".txt", ".json", ".yaml", ".yml", ".sh", ".html",
            ".js", ".ts", ".css", ".csv", ".bat", ".ps1"}

# ---- 包内替换规则（顺序敏感）----
REPS = [
    (r"C:\Users\lenmo\.zcode\workspace\novels\\", "~/novels/"),
    (r"C:\Users\lenmo\.zcode\skills\网络小说创作技能", "~/.workbuddy/skills/网络小说创作技能"),
    (r"C:\Users\lenmo\.zcode\skills", "~/.workbuddy/skills"),
    (r"C:\Users\lenmo", "~"),
    ("C:/Users/lenmo", "~"),
    ("~/.zcode/skills/", "~/.workbuddy/skills/"),
    (".zcode/skills/", ".workbuddy/skills/"),
    ("`$CODEX_HOME`", "工具缓存目录"),
    ("ZCode", "WorkBuddy"),
    ("zcode", "workbuddy"),
    ("|tools|", "|scripts|"),
    ("tools/", "scripts/"),
]

FM_INSERT = """display_name: 网络小说创作技能
display_name_en: Web Novel Studio
description_zh: "面向超长篇网文的工业化创作引擎：一个入口覆盖初始化项目、写章续写、短篇、短剧剧本、扫榜选题、拆书学习、导入旧书、审校诊断、去AI味、通读顺滑、扩写润色、朱雀/墨尺AI检测、封面生成、可视化看板与无人值守日更；每章强制跑 30 项校验（脚本硬卡 13 + AI 语义 17），不达标禁止交付。"
description_en: "An industrial-grade writing engine for long-form Chinese web novels: project setup, chapter drafting, short stories, vertical-drama scripts, market trend research, book deconstruction, legacy manuscript import, review, AI-flavor removal, read-through smoothing, cover generation, dashboards and unattended daily writing. Every chapter must pass a 30-item quality gate before delivery."
category: writing
version: %s
author: 豫晨""" % VER


def log(*a):
    print(*a)


# ---------- 1. 复制 ----------
if os.path.exists(STAGE_ROOT):
    shutil.rmtree(STAGE_ROOT)
os.makedirs(STAGE)

copied = 0
for dp, dns, fns in os.walk(ROOT):
    rel = os.path.relpath(dp, ROOT)
    if rel == ".":
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
    else:
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
    for fn in fns:
        if fn in EXCLUDE_FILES or fn.endswith(".pyc"):
            continue
        src = os.path.join(dp, fn)
        relp = os.path.relpath(src, ROOT)
        dst = os.path.join(STAGE, relp)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
log("[1/6] 复制完成：%d 个文件" % copied)

# ---------- 2. tools/ -> scripts/ ----------
old_tools = os.path.join(STAGE, "tools")
new_scripts = os.path.join(STAGE, "scripts")
if os.path.isdir(old_tools):
    os.rename(old_tools, new_scripts)
    log("[2/6] 目录重命名：tools/ -> scripts/")

# ---------- 3. 文本替换 ----------
changed, total = 0, 0
for dp, _, fns in os.walk(STAGE):
    for fn in fns:
        p = os.path.join(dp, fn)
        if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
            continue
        total += 1
        try:
            t = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        o = t
        for a, b in REPS:
            t = t.replace(a, b)
        if t != o:
            open(p, "w", encoding="utf-8", newline="").write(t)
            changed += 1
log("[3/6] 文本脱敏/改写：%d/%d 个文本文件被修改" % (changed, total))

# ---------- 4. 补全 frontmatter ----------
skill_md = os.path.join(STAGE, "SKILL.md")
t = open(skill_md, encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
if not m:
    log("!! SKILL.md frontmatter 解析失败，终止")
    sys.exit(1)
fm = m.group(1)
# WorkBuddy 要求 name 为 kebab-case（小写字母/数字/连字符），中文名走 display_name
fm = re.sub(r"(?m)^name:\s*.*$", "name: web-novel-writing", fm, count=1)
if "display_name:" not in fm:
    fm_new = fm.rstrip() + "\n" + FM_INSERT
    t = "---\n" + fm_new + "\n---\n" + t[m.end():]
    open(skill_md, "w", encoding="utf-8", newline="").write(t)
    log("[4/6] frontmatter 补全：display_name / display_name_en / description_zh / description_en / category / version / author")
else:
    log("[4/6] frontmatter 已含平台字段，跳过")

# ---------- 5. 残留体检 ----------
log("[5/6] 包内残留扫描")
BAD = [
    ("个人路径 lenmo", re.compile(r"[Cc]:[\\/]Users[\\/]lenmo")),
    ("旧平台 ZCode", re.compile(r"[Zz][Cc]ode")),
    ("旧目录 tools/", re.compile(r"\btools/")),
    ("CODEX_HOME", re.compile(r"CODEX_HOME")),
    ("密钥样式", re.compile(r"sk-[A-Za-z0-9\-_]{16,}")),
]
found = 0
for dp, _, fns in os.walk(STAGE):
    for fn in fns:
        p = os.path.join(dp, fn)
        if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
            continue
        txt = open(p, encoding="utf-8", errors="ignore").read()
        for label, pat in BAD:
            hits = pat.findall(txt)
            if hits:
                found += 1
                log("    !! %s <- %s (%d)" % (label, p.replace(STAGE, "")[1:], len(hits)))
if not found:
    log("    干净：无个人路径 / 旧平台名 / 旧目录名 / 密钥残留")

# ---------- 6. 文件清单 + 校验 + 打包 ----------
files = []
for dp, _, fns in os.walk(STAGE):
    for fn in fns:
        p = os.path.join(dp, fn)
        files.append(os.path.relpath(p, STAGE_ROOT).replace("\\", "/"))
files.sort()
log("[6/6] 包内 %d 个文件，合计 %.2f MB（ZIP 上限 3MB）" % (
    len(files), sum(os.path.getsize(os.path.join(STAGE_ROOT, f)) for f in files) / 1024 / 1024))
for f in files:
    log("    " + f)

os.makedirs(DIST, exist_ok=True)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f in files:
        z.write(os.path.join(STAGE_ROOT, f), f)
log("\nZIP: %s  (%.2f MB)" % (ZIP_PATH, os.path.getsize(ZIP_PATH) / 1024 / 1024))

# 引用完整性校验
cr = os.path.join(STAGE, "scripts", "check_refs.py")
if os.path.exists(cr):
    r = subprocess.run([sys.executable, cr], capture_output=True, text=True, encoding="utf-8", cwd=STAGE)
    log("\ncheck_refs.py 退出码=%s" % r.returncode)
    out = (r.stdout or "") + (r.stderr or "")
    log(out[-1500:] if out else "(无输出)")
