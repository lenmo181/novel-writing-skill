# -*- coding: utf-8 -*-
"""bump_version.py — 网络小说创作技能 v7.51 一键改版工具。

背景
----
v7.42 发布时，改版需要人工同步 17 个文件、63 处版本字符串；`config.py` 的
`RELEASE_DATE` 从 2026-10-07 改成 2026-10-09 时，两处测试副本没跟上，
CI 三门矩阵全红。根因是「改版点散落且无清单」，本工具把它变成配置 + 一条命令。

设计
----
* 点位清单配置化：每个点位声明「文件 + 原串 + 新串 + 期望命中次数」。
  命中 0 次 = 漏改（报错），命中次数与期望不符 = 误改风险（报错）。
* 双模式：`--dry-run`（默认）只打印，`--apply` 才落盘。
* 残留扫描：改完仍出现旧版本号的文件会被点名，交由人工确认——
  版本标签型（如「v7.42：章节语义证据 Gate」）不该被批量改写。
* 改完自校验：串跑 lint_skill.py → check_refs.py → doctor.py。

用法
----
    python tools/bump_version.py --to 7.43 --date 2026-10-12 --title "发布链工程化版"
    python tools/bump_version.py --to 7.43 --date 2026-10-12 --title "…" --apply
    python tools/bump_version.py --to 7.43 --date 2026-10-12 --title "…" --apply --no-verify

退出码：0=成功 / 1=点位异常或校验失败 / 2=参数错误
"""
import argparse
import difflib
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 扫描残留时跳过：历史归档、构建产物、宿主元数据、缓存
# v7.47：补 packaging/assets/tests——与 doctor.py TREE_EXCLUDED_PARTS 对齐。
# 此前 dry-run 残留输出大半是 packaging/** 构建副本树，每版重复刷屏，
# 淹没真正的版本标签残留（tools/doctor.py、README.md）
SKIP_DIRS = {".git", ".workbuddy", ".playwright-cli", ".v2c", ".video_agent",
             "__pycache__", "dist", "out", "versions", ".github",
             "packaging", "assets", "tests"}

VERSION_RE = re.compile(r"^\d+\.\d+$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ────────────────────────────── 点位清单 ──────────────────────────────
# 三条约定：
#   1. 只登记「当前版本标记」；版本标签型（某版新增功能的标题）不登记，
#      由残留扫描交人工确认，避免把历史标签改写成新版本号。
#   2. expect 必填，宁可报错也不模糊替换。
#   3. 真源是 config.py，其余全是它的投影。
def build_rules(old, new, old_date, new_date, title, summary):
    """返回规则列表；每项含 type/file/old/new/expect。"""
    rules = []

    def rep(path, old_s, new_s, expect=1):
        rules.append({"type": "replace", "file": path, "old": old_s,
                      "new": new_s, "expect": expect})

    def rgx(path, pattern, new_s, expect=1):
        rules.append({"type": "regex", "file": path, "old": pattern,
                      "new": new_s, "expect": expect})

    def ins(path, anchor, text, expect=1):
        rules.append({"type": "insert_before", "file": path, "old": anchor,
                      "new": text, "expect": expect})

    # 1) 版本真源
    rep("tools/config.py", f'SKILL_VERSION = "{old}"', f'SKILL_VERSION = "{new}"')
    rep("tools/config.py", f'RELEASE_DATE = "{old_date}"', f'RELEASE_DATE = "{new_date}"')

    # 2) SKILL.md：frontmatter 版本号 + 版本行（整行重写，含发布日期与版本别名）
    rep("SKILL.md", f"version: {old}.0", f"version: {new}.0")
    rgx("SKILL.md", rf"^> \*\*版本\*\*：v{re.escape(old)}（{old_date}）.+$",
        f"> **版本**：v{new}（{new_date}）· {title}")

    # 3) README.md：当前版本行、本轮亮点段（insert_before 保留历史段）、最近版本重点新增一条
    # 历史教训：此处原为 rep「## v{old} 本轮升级重点」→「## v{new} 本轮升级重点」，
    # 只推标题版本号、内容原地不动。改版后忘了重写该段，上一版内容就挂到新版本
    # 名下（v7.44 段在 v7.45 名下挂了整整一轮）。改为与 CHANGELOG 同构的
    # insert_before：新段插在旧段之前，旧段标题永远归属正确版本。
    rep("README.md", f"当前版本：v{old}**（{old_date}）", f"当前版本：v{new}**（{new_date}）")
    ins("README.md", f"## v{old} 本轮升级重点",
        f"## v{new} 本轮升级重点\n\n- 待补：本轮新增或变更的能力\n\n")
    rep("README.md", f"当前版本：**v{old}**", f"当前版本：**v{new}**")
    ins("README.md", f"- **v{old}**：", f"- **v{new}**：{summary}\n")

    # 4) 运行时手册版本台账：38 行全量投影，命中次数不固定
    # v7.47：边界正则——此前裸子串替换，若台账出现 "v7.46.1" 热修复条目，
    # 会被静默改成 "v7.47.1"（将来一旦出现补号变体即静默损坏）
    rules.append({"type": "regex", "file": "references/版本台账.md",
                  "old": rf"(?<![\d.])v{re.escape(old)}(?![\d.])", "new": f"v{new}", "expect": None})
    # 5) 其余运行时手册的「当前版本」标记
    rep("references/评测场景.md", f"v{old}", f"v{new}", expect=2)
    rep("references/语义审校.md", f"语义审校与第14-30项证据（v{old}）",
        f"语义审校与第14-30项证据（v{new}）")

    # 6) 工具 docstring 版本标记（逐个定点，避免误伤注释里的历史引用）
    rep("tools/bump_version.py", f"网络小说创作技能 v{old} 一键改版工具",
        f"网络小说创作技能 v{new} 一键改版工具")
    # v7.47：MCP Server 版本号纳入登记——此前 SERVER_VERSION 手工同步，
    # 与 config.SKILL_VERSION 两处版本源存在漂移可能
    rep("packaging/mcp/server.py", f'SERVER_VERSION = "{old}.0"', f'SERVER_VERSION = "{new}.0"')
    rep("packaging/mcp/server.json", f'"version": "{old}.0"', f'"version": "{new}.0"', expect=2)
    rgx("README.en.md", rf"^> \*\*Version: v{re.escape(old)}\*\* \({re.escape(old_date)}\).*$",
        f"> **Version: v{new}** ({new_date}) · Author: Yuchen (豫晨) · License: Apache-2.0")
    rep("tools/chapter_readiness.py", f"章节交付 Gate（v{old}）", f"章节交付 Gate（v{new}）")
    rep("tools/doctor.py", f"技能包统一自检（v{old}）", f"技能包统一自检（v{new}）")
    rep("tools/eval_skill.py", f"评测场景矩阵校验器（v{old}）", f"评测场景矩阵校验器（v{new}）")
    rep("tools/full_review.py", f"全文审稿流水线（v{old}）", f"全文审稿流水线（v{new}）")
    rep("tools/lint_skill.py", f"技能包版本治理检查器（v{old}）", f"技能包版本治理检查器（v{new}）")
    rep("tools/mochi_setup.py", f"网络小说创作技能 v{old} 墨尺一键安装向导",
        f"网络小说创作技能 v{new} 墨尺一键安装向导")
    rep("tools/release_check.py", f"发布前只读预检（v{old}）", f"发布前只读预检（v{new}）")
    rep("tools/repair_orchestrator.py", f"全文修复编排器（v{old}）", f"全文修复编排器（v{new}）")
    rep("tools/repair_runner.py", f"全文审稿修复队列状态执行层（v{old}）",
        f"全文审稿修复队列状态执行层（v{new}）")
    rep("tools/update_skill.py", f"检查并安全更新网络小说创作技能（v{old}）",
        f"检查并安全更新网络小说创作技能（v{new}）")

    # 7) CHANGELOG：按四段式插入新版本条目（更新/修复/降级删除/验证证据）
    skeleton = (
        f"## v{new}（{new_date}）：{title}\n\n"
        "### 更新\n\n- 待补：本轮新增或变更的能力\n\n"
        "### 修复\n\n- 待补：本轮修掉的缺陷；无外部缺陷上报时写明「本版为功能与治理维护轮」\n\n"
        "### 降级删除\n\n- 待补：本轮移除的能力、口径或不再维护的承诺\n\n"
        "### 验证证据\n\n- 待补：回归条数、四件套结果、真机实测结论\n\n---\n\n"
    )
    ins("versions/CHANGELOG.md", f"## v{old}（{old_date}）", skeleton)
    return rules


# ────────────────────────────── 执行与校验 ──────────────────────────────
def apply_to_text(text, rules):
    """对单个文件的文本应用规则，返回 (新文本, 命中列表, 错误列表)。"""
    hits, errors = [], []
    for rule in rules:
        old_s, expect = rule["old"], rule["expect"]
        if rule["type"] == "regex":
            found = re.findall(old_s, text, re.M)
            if expect is not None and len(found) != expect:
                errors.append(f"命中 {len(found)} 次，期望 {expect} 次：{old_s}")
                continue
            text = re.sub(old_s, rule["new"].replace("\\", "\\\\"), text, count=0, flags=re.M)
            hits.append(f"regex ×{len(found)}")
        elif rule["type"] == "insert_before":
            idx = text.find(old_s)
            if idx < 0:
                errors.append(f"锚点未找到：{old_s[:60]}")
                continue
            if expect is not None and text.count(old_s) != expect:
                errors.append(f"锚点出现 {text.count(old_s)} 次，期望 {expect} 次：{old_s[:60]}")
                continue
            text = text[:idx] + rule["new"] + text[idx:]
            hits.append("insert ×1")
        else:  # replace
            n = text.count(old_s)
            if n == 0:
                errors.append(f"未找到：{old_s[:60]}")
                continue
            if expect is not None and n != expect:
                errors.append(f"命中 {n} 次，期望 {expect} 次：{old_s[:60]}")
                continue
            text = text.replace(old_s, rule["new"])
            hits.append(f"×{n}")
    return text, hits, errors


def scan_residue(old, replaced):
    """扫描**应用规则之后**仍残留旧版本号的文件。

    replaced: {相对路径: 规则应用后的文本}。版本标签型（如「v7.42：章节语义证据 Gate」）
    本就不该被批量改写，这里只做点名，交由人工确认，不算错误。
    """
    out = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix not in {".py", ".md", ".json", ".ps1", ".yml", ".yaml", ".txt"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in replaced:
            text = replaced[rel]
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        if old in text:
            # v7.47：边界断言防假阳性——此前裸子串，"7.46" 命中 "17.46"/"7.460"
            lines = [i for i, ln in enumerate(text.splitlines(), 1)
                     if re.search(rf"(?<![\d.])v?{re.escape(old)}(?![\d.])", ln)]
            if lines:
                out.append((rel, lines))
    return out


def verify():
    """改版后自校验：lint → check_refs → doctor。"""
    for script in ("lint_skill.py", "check_refs.py", "doctor.py"):
        # v7.47：显式 UTF-8——此前未传 encoding，中文 Windows 普通 cmd 下按 cp936
        # 解码，读取线程抛 UnicodeDecodeError：终端灌满 traceback、proc.stdout
        # 解码后为空，校验真失败时 tail[-3:] 取到空列表、真实错误信息全部丢失，
        # 成功路径"假绿式安静"（已实测复现）。与 doctor.py 正确写法对齐。
        proc = subprocess.run([sys.executable, f"tools/{script}"], cwd=ROOT,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        tail = (proc.stdout or "").strip().splitlines()
        if proc.returncode != 0:
            return False, f"{script} 失败：{tail[-3:] if tail else (proc.stderr or '')[-300:]}"
    return True, "lint / check_refs / doctor 全绿"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="一键改版：把版本与发布日期同步到全部登记点位")
    parser.add_argument("--to", required=True, help="目标版本，如 7.43")
    parser.add_argument("--date", required=True, help="发布日 YYYY-MM-DD")
    parser.add_argument("--title", required=True, help="版本别名，如「发布链工程化版」")
    parser.add_argument("--summary", default="", help="README 最近版本重点一句话；缺省用 title")
    parser.add_argument("--from", dest="from_v", default="", help="当前版本；缺省从 config.py 读")
    parser.add_argument("--apply", action="store_true", help="真正落盘；缺省为 dry-run")
    parser.add_argument("--no-verify", action="store_true", help="跳过改版后的 lint/refs/doctor")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "tools"))
    import config  # noqa: E402

    new, new_date = args.to.strip(), args.date.strip()
    # v7.47：--from 格式校验——此前 old（来自 --from 或 config）无校验，笔误即
    # 静默损坏：--from 7.4（漏一位）→ 规则变裸子串替换 "v7.4"→"v7.5x"，
    # 版本台账规则 expect=None 不计数不报错，把 "v7.46" 改成 "v7.56" 落盘损坏
    old = (args.from_v.strip() or config.SKILL_VERSION).strip()
    if not VERSION_RE.match(old):
        print(f"[✗] 当前版本格式非法：{old}（应为 主.次，如 7.46）")
        return 2
    if old == new:
        print(f"[✗] 目标版本与当前版本相同（v{new}）：无需改版")
        return 2
    old_date = config.RELEASE_DATE
    summary = args.summary.strip() or args.title.strip()

    if not VERSION_RE.match(new):
        print(f"[✗] 目标版本格式非法：{new}（应为 主.次，如 7.43）")
        return 2
    if not ISO_RE.match(new_date):
        print(f"[✗] 发布日期格式非法：{new_date}（应为 YYYY-MM-DD）")
        return 2
    try:
        if datetime.strptime(new_date, "%Y-%m-%d").date() > date.today():
            print(f"[✗] 发布日期不能是未来：{new_date}")
            return 2
    except ValueError:
        print(f"[✗] 发布日期不是合法日历日：{new_date}")
        return 2

    rules = build_rules(old, new, old_date, new_date, args.title.strip(), summary)

    # 按文件分组
    by_file = {}
    for rule in rules:
        by_file.setdefault(rule["file"], []).append(rule)

    mode = "APPLY" if args.apply else "DRY-RUN"
    # v7.47：从 config 读版本——此前硬编码 "v7.43"，已停留三个版本；
    # 且残留扫描扫的是旧版本号而非工具版本，永远发现不了这处漂移
    print(f"网络小说创作技能改版工具 v{config.SKILL_VERSION}  [{mode}]")
    print(f"版本：v{old}（{old_date}） → v{new}（{new_date}）· {args.title.strip()}")
    print(f"点位：{len(rules)} 条 / {len(by_file)} 个文件\n")

    all_errors, changed, replaced = [], [], {}
    # v7.47：两阶段——先全部算完（只读），确认零错误才进入写盘阶段。
    # 此前循环内逐文件落盘：第 N 个点位错误（continue 跳过）时前 N-1 个
    # 已写盘，工具退出码 1 但仓库处于混合版本状态；单文件写一半崩溃
    # （断电/磁盘满/占用）还会留下截断损坏的文件（write_text 无 tmp+rename）
    for rel in sorted(by_file):
        path = ROOT / rel
        if not path.is_file():
            all_errors.append(f"{rel}：文件不存在")
            continue
        # v7.47：newline="" 保留原行尾——read_text/write_text 通用换行往返会把
        # LF 检出的仓库碰过的文件整体变 CRLF，制造巨量 diff
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as exc:
            all_errors.append(f"{rel}：读取失败（{exc.__class__.__name__}）")
            continue
        new_text, hits, errors = apply_to_text(text, by_file[rel])
        replaced[rel] = new_text
        if errors:
            for e in errors:
                all_errors.append(f"{rel}：{e}")
            print(f"[✗] {rel}（{len(by_file[rel])} 点位）未通过")
            continue
        # 插入会平移行号，逐行 zip 比不了，用 difflib 数真实增删行
        # v7.47：diff 头部判定 "+++ "/"--- "（带空格）——此前 startswith("---")
        # 把 markdown 水平线 "----" 也排除，含水平线的文件"将变更行数"少数
        diff = difflib.unified_diff(text.splitlines(), new_text.splitlines(), n=0)
        n_diff = sum(1 for ln in diff
                     if ln[:1] in ("+", "-") and not ln.startswith(("+++ ", "--- ")))
        changed.append(rel)
        print(f"[✓] {rel}：{len(by_file[rel])} 点位，{n_diff} 行将变更（{'，'.join(hits)}）")

    if all_errors:
        print("\n结论：点位异常，未落盘")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    if args.apply:
        # 第二阶段：零错误才统一落盘，单文件 tmp + os.replace 原子写 + .bak
        for rel in changed:
            path = ROOT / rel
            try:
                if path.exists():
                    path.with_suffix(path.suffix + ".bak").write_text(
                        path.read_text(encoding="utf-8"), encoding="utf-8")
                tmp = path.with_suffix(path.suffix + ".tmp")
                with open(tmp, "w", encoding="utf-8", newline="") as f:
                    f.write(replaced[rel])
                os.replace(tmp, path)
            except OSError as exc:
                print(f"[✗] {rel} 落盘失败：{exc}")
                return 1

    residue = scan_residue(old, replaced)
    if residue:
        print("\n[i] 仍含旧版本号的文件（多为版本标签型，请人工确认是否该保留）：")
        for rel, lines in residue:
            print(f"  - {rel}：第 {lines[:6]}{'…' if len(lines) > 6 else ''} 行")

    if not args.apply:
        print(f"\n结论：dry-run 通过，{len(changed)} 个文件待改；确认后加 --apply")
        return 0

    if args.no_verify:
        print("\n[i] 已跳过自校验（--no-verify）")
        print(f"结论：已改版到 v{new}（{new_date}），{len(changed)} 个文件已落盘")
        return 0

    ok, msg = verify()
    print(f"\n[{'✓' if ok else '✗'}] 自校验：{msg}")
    if not ok:
        print("结论：改版已落盘但自校验未通过——请用 git 回滚后再排查：git checkout -- .")
        return 1
    print(f"结论：已改版到 v{new}（{new_date}），{len(changed)} 个文件已落盘，自校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
