# -*- coding: utf-8 -*-
"""章节版本差异与大删风险检查（v7.34）。"""
import argparse
import difflib
import json
import sys
from pathlib import Path

from config import DEFAULT_DIFF_DELETE_WARN, SKILL_VERSION
from check_chapter import body_lines, count_chars, dialogue_chars, dialogue_span_re, load_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def metrics(text: str, quote="chal"):
    # v7.47：metrics 改为接收已读入的文本而非路径，配合 build_report 每侧只读盘一次
    lines, _ = body_lines(text)
    body = "\n".join(lines)
    total = count_chars(body)
    dialog = dialogue_chars(body, dialogue_span_re(quote))
    return {
        "chars": total,
        "dialog_chars": dialog,
        "dialog_ratio": round(dialog / total * 100, 2) if total else 0.0,
        "lines": len(lines),
    }


def build_report(before: Path, after: Path, warn=DEFAULT_DIFF_DELETE_WARN, max_lines=160, quote="chal"):
    before_text = load_text(str(before))  # v7.47：每侧只读盘一次，文本直接传给 metrics，不再重复 IO
    after_text = load_text(str(after))
    before_metrics = metrics(before_text, quote)
    after_metrics = metrics(after_text, quote)
    diff_lines = list(difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        fromfile=str(before),
        tofile=str(after),
        lineterm="",
    ))
    removed_chars = max(0, before_metrics["chars"] - after_metrics["chars"])
    delete_ratio = removed_chars / before_metrics["chars"] if before_metrics["chars"] else 0.0
    # v7.47：统计 diff 中真实删除行（- 开头且非 --- 文件头），识别等字数改写：
    # 整章同字数重写时删除比例为 0 不触发大删预警，但伏笔/钩子可能已被洗掉
    deleted_lines = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    same_chars_rewrite = before_metrics["chars"] == after_metrics["chars"] and deleted_lines > 0
    return {
        "version": SKILL_VERSION,
        "before": str(before),
        "after": str(after),
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "removed_chars": removed_chars,
        "added_chars": max(0, after_metrics["chars"] - before_metrics["chars"]),
        "delete_ratio": round(delete_ratio, 4),
        "delete_warn": warn,
        "large_delete": delete_ratio > warn,
        "deleted_lines": deleted_lines,
        "same_chars_rewrite": same_chars_rewrite,
        "diff_lines": diff_lines[:max_lines],
        "diff_truncated": len(diff_lines) > max_lines,
    }


def render(report):
    b = report["before_metrics"]
    a = report["after_metrics"]
    lines = [
        f"# 章节版本差异（v{report['version']}）",
        "",
        f"- 修改前：`{report['before']}`",
        f"- 修改后：`{report['after']}`",
        "",
        "| 指标 | 修改前 | 修改后 | 变化 |",
        "|---|---:|---:|---:|",
        f"| 正文字数 | {b['chars']} | {a['chars']} | {a['chars'] - b['chars']} |",
        f"| 对话占比 | {b['dialog_ratio']:.2f}% | {a['dialog_ratio']:.2f}% | {a['dialog_ratio'] - b['dialog_ratio']:.2f}pp |",
        f"| 正文行数 | {b['lines']} | {a['lines']} | {a['lines'] - b['lines']} |",
        f"| 删除比例 | - | - | {report['delete_ratio'] * 100:.2f}% |",
        "",
        "## 风险",
        "",
        (f"[!] 删除比例超过 {report['delete_warn'] * 100:.0f}%；请复核伏笔、钩子、因果锚点和人物状态后再覆盖原稿。"
         if report["large_delete"] else "[✓] 未超过默认大删预警线。"),
        # v7.47：等字数改写（字数差=0 但有删除行）删除比例为 0 不触发大删预警，补一条人工过目警告
        *([f"[!] 等字数改写：正文字数差为 0 但删除 {report['deleted_lines']} 行——伏笔/钩子可能被同字数洗掉，请人工过目后再覆盖原稿。"]
          if report["same_chars_rewrite"] else []),
        "",
        "## 差异",
        "",
        "```diff",
        "\n".join(report["diff_lines"]),
        "```",
    ]
    if report["diff_truncated"]:
        lines.extend(["", f"> 差异已截断，仅展示前 {len(report['diff_lines'])} 行。"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=f"章节版本差异与大删风险检查 v{SKILL_VERSION}")
    parser.add_argument("before", help="修改前章节文件")
    parser.add_argument("after", help="修改后章节文件")
    parser.add_argument("--warn", type=float, default=DEFAULT_DIFF_DELETE_WARN, help=f"删除比例预警线（默认{DEFAULT_DIFF_DELETE_WARN * 100:.0f}%%）")
    parser.add_argument("--max-diff-lines", type=int, default=160)
    # v7.47：新增 --quote 口径参数，透传给 dialogue_span_re，与 check_chapter 的对话占比口径一致
    parser.add_argument("--quote", choices=["chal", "straight", "any"], default="chal",
                        help="对话占比口径：chal/straight/any（默认 chal，与 check_chapter 一致）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--strict", action="store_true", help="超过删除预警线时退出码为1")
    args = parser.parse_args()
    before = Path(args.before).expanduser()
    after = Path(args.after).expanduser()
    if not before.is_file() or not after.is_file():
        print("[✗] 修改前和修改后文件都必须存在")
        return 2
    if not 0 <= args.warn <= 1 or args.max_diff_lines < 20:
        print("[✗] --warn 必须在0-1之间，--max-diff-lines必须不小于20")
        return 2
    report = build_report(before, after, args.warn, args.max_diff_lines, args.quote)
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
    if args.out:
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"差异报告已写入：{target}")
    else:
        print(output, end="")
    return 1 if args.strict and report["large_delete"] else 0


if __name__ == "__main__":
    sys.exit(main())
