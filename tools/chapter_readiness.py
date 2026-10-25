# -*- coding: utf-8 -*-
"""章节交付 Gate（v7.50）：默认工程 Gate + 可验证语义 Gate。

v7.49：语义 Gate 增加「证据引文不可篡改校验」——对标 AI_NovelGenerator 的
CHAPTER_CHECK_QUOTE_MISMATCH。此前 evidence 只校验「非空字符串」，AI 可以
写一段根本不存在的「原文摘录」照样通过；现在 evidence 支持
{text, quote, offset} 结构，服务端按 offset 逐字比对正文，quote 与正文不符
即判失败（引文锚点不可伪造）。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from config import SKILL_VERSION

TOOLS = Path(__file__).resolve().parent
SEMANTIC_DIR = Path("mind") / "审校"
SEMANTIC_CHECKS = list(range(14, 31))
# v7.44：weak = 未经 AI 语义复核的机械弱证据档
VALID_SEMANTIC_STATUS = {"pass", "warn", "revise", "blocked", "weak"}


def read_chapter_text(path):
    """读章节正文用于引文比对；沿用三级编码回退，与 canonical_parser 同源口径。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def verify_quote(chapter_text, quote, offset):
    """校验引文锚点：正文[offset:offset+len(quote)] 必须逐字等于 quote。

    返回 (ok, detail)。offset 越界、切片不等于 quote 均判失败。
    契约：offset 以**字符**为单位（不是字节），与 Python 切片一致。
    """
    if not isinstance(quote, str) or not quote:
        return False, "quote 为空"
    if not isinstance(offset, int) or isinstance(offset, bool):
        return False, "offset 必须是整数"
    if offset < 0:
        return False, "offset 为负数"
    if offset + len(quote) > len(chapter_text):
        return False, (f"offset={offset} + len(quote)={len(quote)} 超出正文长度 "
                       f"{len(chapter_text)}")
    actual = chapter_text[offset:offset + len(quote)]
    if actual != quote:
        return False, (f"引文与正文不符：offset={offset} 处正文为 "
                       f"「{actual[:24]}」，记录写的是「{quote[:24]}」")
    return True, f"引文锚点校验通过（offset={offset}，{len(quote)} 字）"


def run_gate(name, command, cwd):
    try:
        p = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        output = (p.stdout + "\n" + p.stderr).strip().splitlines()
        return {"name": name, "ok": p.returncode == 0, "exit_code": p.returncode, "tail": output[-6:]}
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "exit_code": 2, "tail": ["超过180秒未返回"]}
    except OSError as exc:
        return {"name": name, "ok": False, "exit_code": 2, "tail": [str(exc)]}

def resolve_chapter(root, chapter):
    candidates = sorted((root / "书稿").glob(f"第{chapter:03d}章*")) + sorted((root / "书稿").glob(f"第{chapter}章*"))
    return next((p for p in candidates if p.is_file()), None)

def semantic_path(root, chapter):
    return root / SEMANTIC_DIR / f"第{chapter:03d}章审校.json"

def semantic_gate(root, chapter):
    path = semantic_path(root, chapter)
    if not path.is_file():
        return {"name": "30项语义证据", "ok": False, "exit_code": 1,
                "tail": [f"缺少 {path.relative_to(root)}；需完成第14-30项语义审校并逐项记录证据"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": [f"审校记录无法解析：{exc}"]}
    if not isinstance(data, dict):
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": ["审校记录必须是 JSON 对象"]}
    if data.get("version") != SKILL_VERSION:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"审校记录 version={data.get('version')} 与当前运行时 v{SKILL_VERSION} 不一致"]}
    if data.get("chapter") != chapter:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"审校记录 chapter={data.get('chapter')} 与目标第{chapter}章不一致"]}
    chapter_file = resolve_chapter(root, chapter)
    if chapter_file is None:
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": ["当前章节无法读取，不能验证语义证据绑定"]}
    try:
        digest = hashlib.sha256(chapter_file.read_bytes()).hexdigest()
    except OSError as exc:
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": [f"章节哈希计算失败：{exc}"]}
    if data.get("chapter_sha256") != digest:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": ["语义证据对应的 chapter_sha256 与当前正文不一致；正文已变更，必须重新审校"]}
    checks = data.get("checks")
    if not isinstance(checks, dict):
        return {"name": "30项语义证据", "ok": False, "exit_code": 2, "tail": ["checks 必须是对象，覆盖校验14-30"]}
    chapter_text = read_chapter_text(chapter_file)
    missing = []
    invalid = []
    failed = []
    weak = []
    quote_mismatch = []
    quote_checked = 0
    for number in SEMANTIC_CHECKS:
        item = checks.get(str(number), checks.get(number))
        if not isinstance(item, dict):
            missing.append(str(number))
            continue
        status = item.get("status")
        if not isinstance(status, str) or status not in VALID_SEMANTIC_STATUS:
            invalid.append(str(number))
        if isinstance(status, str) and status in {"revise", "blocked"}:
            failed.append(number)
        # v7.44 弱证据档：AI 语义复核不可用时用机械证据兜底，不卡死 Gate，
        # 但会拉低 semantic_strength 并让 delivery_ready=False——可继续写，不可当交付结论。
        if isinstance(status, str) and status == "weak":
            weak.append(number)
        evidence = item.get("evidence")
        # ── v7.49 引文不可篡改校验 ──
        # evidence 允许两种形态：
        #   1) 纯字符串（旧格式，只有描述性证据）
        #   2) 对象 {"text": 描述, "quote": 原文摘录, "offset": 字符偏移}
        # 形态 2 走服务端逐字比对：quote 与正文不符即失败，AI 无法编造引文。
        if isinstance(evidence, dict):
            text_value = evidence.get("text")
            if not isinstance(text_value, str) or not text_value.strip():
                invalid.append(f"{number}:evidence.text")
            quote = evidence.get("quote")
            offset = evidence.get("offset")
            if quote is None and offset is None:
                # 只给了 text 没给锚点：不算失败，但本项不具备可验证性
                invalid.append(f"{number}:evidence.quote")
            elif quote is not None or offset is not None:
                quote_checked += 1
                ok, detail = verify_quote(chapter_text, quote, offset)
                if not ok:
                    quote_mismatch.append(f"{number}:{detail}")
        elif not isinstance(evidence, str) or not evidence.strip():
            invalid.append(f"{number}:evidence")
    tail_extra = {}
    if missing:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"缺少语义校验项：{chr(44).join(missing)}"]}
    if invalid:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"语义记录缺少合法 evidence/status：{chr(44).join(invalid[:8])}"]}
    if quote_mismatch:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1,
                "tail": [f"引文与正文不符（{len(quote_mismatch)} 项，不可篡改校验失败）："
                         + quote_mismatch[0]]}
    if failed:
        return {"name": "30项语义证据", "ok": False, "exit_code": 1, "tail": [f"存在未解决语义项：{chr(44).join(map(str, failed))}"]}
    if weak:
        return {"name": "30项语义证据", "ok": True, "exit_code": 0, "weak": weak,
                "quote_checked": quote_checked,
                "tail": [f"第14-30项均有 status + evidence，其中 {len(weak)} 项为 weak 弱证据"
                         f"（{chr(44).join(map(str, weak[:8]))}）：未经 AI 语义复核，Gate 不卡死，"
                         "但 delivery_ready=false，不可作为正式交付结论"]}
    return {"name": "30项语义证据", "ok": True, "exit_code": 0, "quote_checked": quote_checked,
            "tail": [f"第14-30项共{len(SEMANTIC_CHECKS)}项均有 status + evidence"
                     + (f"，{quote_checked} 项引文锚点逐字比对通过" if quote_checked else "")]}

def assess(root, chapter, full=False, with_semantic=True):
    target = resolve_chapter(root, chapter)
    if target is None:
        return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter, "ok": False, "delivery_ready": False, "semantic_required": with_semantic, "input_error": True,
                "gates": [{"name": "章节存在", "ok": False, "exit_code": 2, "tail": [f"未找到第{chapter}章"]}]}
    commands = [
        ("单章机械校验", [sys.executable, str(TOOLS / "check_chapter.py"), str(target)]),
        ("项目健康", [sys.executable, str(TOOLS / "project_health.py"), str(root)]),
        ("连续性检查", [sys.executable, str(TOOLS / "continuity_check.py"), str(root)]),
        ("上下文可构建", [sys.executable, str(TOOLS / "context_pack.py"), str(root), "--chapter", str(chapter), "--format", "json"]),
    ]
    gates = [run_gate(n, c, root) for n, c in commands]
    if with_semantic:
        gates.append(semantic_gate(root, chapter))
    if full:
        gates.append(run_gate("全文审稿", [sys.executable, str(TOOLS / "full_review.py"), str(root), "--strict", "--json", "--no-write"], root))
    weak_items = sorted({n for g in gates for n in g.get("weak", [])})
    return {"version": SKILL_VERSION, "project": str(root), "chapter": chapter,
            "target": str(target.relative_to(root)), "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "semantic_required": with_semantic,
            "semantic_strength": "weak" if weak_items else ("full" if with_semantic else "skipped"),
            "weak_checks": weak_items,
            "semantic_record": str(semantic_path(root, chapter).relative_to(root)) if with_semantic else None,
            "gates": gates, "ok": all(g["ok"] for g in gates),
            "delivery_ready": with_semantic and all(g["ok"] for g in gates) and not weak_items,
            "input_error": False}

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=f"章节交付 Gate v{SKILL_VERSION}")
    ap.add_argument("project"); ap.add_argument("chapter", type=int)
    ap.add_argument("--full", action="store_true", help="额外运行全文审稿 strict")
    semantic_group = ap.add_mutually_exclusive_group()
    semantic_group.add_argument("--with-semantic", dest="with_semantic", action="store_true", default=True, help="默认启用：要求 mind/审校/第XXX章审校.json 覆盖第14-30项并逐项给证据")
    semantic_group.add_argument("--skip-semantic", dest="with_semantic", action="store_false", help="仅做工程 Gate；适合草稿检查，不可作为正式交付结论")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir() or args.chapter < 1:
        print("[✗] 项目目录或章节号非法"); return 2
    report = assess(root, args.chapter, args.full, args.with_semantic)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser(); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(output + "\n", encoding="utf-8"); print(f"交付 Gate 已写入：{target}")
    else:
        print(output)
    return 2 if report.get("input_error") else (0 if report["ok"] else 1)

def render(report):
    lines = [
        f"# 章节交付 Gate（v{report['version']}）",
        "",
        f"- 第 {report['chapter']} 章：`{report.get('target', '-')}`",
        "- 时间：" + report.get("generated_at", ""),
        "",
        "| Gate | 结果 | 退出码 |",
        "|---|---|---:|",
    ]
    for gate in report["gates"]:
        lines.append(f"| {gate['name']} | {'PASS' if gate['ok'] else 'REVISE'} | {gate['exit_code']} |")
    weak_items = report.get("weak_checks") or []
    lines += [
        "",
        "- 语义强度：" + ("full（全部经语义审校）" if report.get("semantic_strength") == "full" else
                       f"weak（{len(weak_items)} 项未经 AI 语义复核：{chr(44).join(map(str, weak_items))}）"
                       if report.get("semantic_strength") == "weak" else "skipped（--skip-semantic）"),
        "",
        "结论：" + ("PASS，可进入交付/作者验收。" if report.get("delivery_ready") else
                    "PASS（弱证据）：Gate 不卡死，可继续写作；但有语义项未经 AI 复核，需人工过目，"
                    "不可作为正式交付结论。" if report["ok"] and report.get("semantic_strength") == "weak" else
                    "草稿工程检查通过；未执行语义 Gate，不可作为正式交付结论。" if report["ok"] else
                    "REVISE，先处理失败 Gate。"),
        "",
        "语义 Gate 需要第14-30项逐项 evidence；本工具只验证记录完整性，不代替作者/AI做文学判断。",
        "weak 档由机械证据兜底产生（`review_skeleton.py --status weak`），AI 可用时应回填为 pass/warn/revise。",
        "失败 Gate 的详细输出已保留在 JSON 报告中；本工具不修改正文。",
    ]
    return "\n".join(lines)

if __name__ == "__main__":
    raise SystemExit(main())
