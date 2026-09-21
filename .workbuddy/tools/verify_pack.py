# -*- coding: utf-8 -*-
"""上架包自检：脚本可执行性 + ZIP 结构校验"""
import os, sys, subprocess, zipfile, json

STAGE = r"C:\Users\lenmo\Desktop\网络小说创作技能\.workbuddy\tmp\stage\网络小说创作技能"
ZIP = r"C:\Users\lenmo\Desktop\网络小说创作技能\dist\网络小说创作技能_v7.25.0_market.zip"

print("=== 脚本可执行性（--help） ===")
sd = os.path.join(STAGE, "scripts")
bad = []
for fn in sorted(os.listdir(sd)):
    if not fn.endswith(".py"):
        continue
    p = os.path.join(sd, fn)
    r = subprocess.run([sys.executable, p, "--help"], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", cwd=STAGE, timeout=60)
    ok = r.returncode == 0 or "usage" in (r.stdout or "").lower() or "用法" in (r.stdout or "")
    print("  %-26s exit=%s %s" % (fn, r.returncode, "OK" if ok else "!! 异常"))
    if not ok:
        bad.append((fn, (r.stdout or "")[-300:], (r.stderr or "")[-300:]))
for fn, o, e in bad:
    print("    %s\n      out=%s\n      err=%s" % (fn, o, e))

print("\n=== ZIP 结构校验 ===")
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    roots = {n.split("/")[0] for n in names}
    depth = max(len(n.split("/")) for n in names)
    print("  顶层条目: %s" % roots)
    print("  最大层级: %d（平台要求 ≤2 层，references/xxx.md 计为 2）" % depth)
    print("  文件数: %d  |  解压后: %.2f MB" % (len(names), sum(i.file_size for i in z.infolist()) / 1024 / 1024))
    print("  含 SKILL.md: %s" % any(n.endswith("SKILL.md") for n in names))
    print("  含可执行脚本: %d 个" % sum(1 for n in names if "/scripts/" in n))
    bad_ent = [n for n in names if n.startswith(".") or "__MACOSX" in n or n.endswith(".pyc")]
    print("  垃圾条目: %s" % (bad_ent or "无"))
    # 检查 zip 内 SKILL.md frontmatter
    fm = z.read([n for n in names if n.endswith("SKILL.md")][0]).decode("utf-8").split("---")[1]
    keys = [l.split(":")[0] for l in fm.strip().split("\n") if ":" in l]
    print("  frontmatter 字段: %s" % keys)
