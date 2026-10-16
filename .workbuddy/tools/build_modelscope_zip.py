# -*- coding: utf-8 -*-
"""
魔搭 ModelScope Skills 中心上架包构建器
- 复用 build_market_zip.py 的 stage 目录（已完成 脱敏 / tools→scripts / frontmatter 补全）
- 输出「ZIP 根目录恰好 1 个 SKILL.md」的扁平结构（魔搭 OpenAPI 上传要求）
- 源目录与通用上架包均不改动
"""
import os
import re
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_NAME = "网络小说创作技能"

CONFIG = Path(ROOT, "tools", "config.py").read_text(encoding="utf-8")
M = re.search(r'^SKILL_VERSION = ["\'](\d+\.\d+)["\']', CONFIG, re.M)
if not M:
    raise SystemExit("tools/config.py 未找到 SKILL_VERSION")
MINOR = M.group(1)          # 7.46
VER = MINOR + ".0"          # 7.46.0

STAGE = Path(ROOT, ".workbuddy", "tmp", "stage_v" + MINOR, SKILL_NAME)
DIST = Path(ROOT, "dist")
OUT = DIST / ("%s_v%s_modelscope.zip" % (SKILL_NAME, VER))

if not STAGE.is_dir():
    raise SystemExit(
        "未找到构建暂存目录：%s\n请先运行 build_market_zip.py 生成 stage。" % STAGE
    )

files = []
for dp, _, fns in os.walk(STAGE):
    for fn in fns:
        p = Path(dp, fn)
        files.append((p, str(p.relative_to(STAGE)).replace("\\", "/")))
files.sort(key=lambda t: t[1])

root_skill = [r for _, r in files if r == "SKILL.md"]
if len(root_skill) != 1:
    raise SystemExit("ZIP 根目录 SKILL.md 数量为 %d 个，必须恰好 1 个" % len(root_skill))

DIST.mkdir(exist_ok=True)
pending = str(OUT) + ".pending"
with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p, r in files:
        z.write(p, r)
os.replace(pending, str(OUT))

print("魔搭包：%s" % OUT.name)
print("  结构：根目录 SKILL.md ✓（恰好 1 个）")
print("  条目：%d 个文件，%.2f MB" % (len(files), OUT.stat().st_size / 1024 / 1024))
