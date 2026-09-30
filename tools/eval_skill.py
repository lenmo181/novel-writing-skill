# -*- coding: utf-8 -*-
"""评测场景矩阵校验器（v7.34）。

只校验本地评测矩阵是否完整、可解析、与主技能入口一致；
它不伪造 SkillHub 分数，也不替代真实模型行为评测。
退出码：0=矩阵通过，1=矩阵有问题，2=输入错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import SKILL_VERSION


ROOT = Path(__file__).resolve().parents[1]
MATRIX_REL = Path("references") / "评测场景.md"
EXPECTED_IDS = [f"EV-{index:02d}" for index in range(1, 17)]
ID_RE = re.compile(r"^EV-\d{2}$")


def parse_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 5:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5 or not ID_RE.match(cells[0]):
            continue
        rows.append({
            "id": cells[0],
            "request": cells[1],
            "route": cells[2],
            "allowed": cells[3],
            "boundary": cells[4],
        })
    return rows


def audit(root: Path = ROOT) -> dict:
    root = Path(root).expanduser().resolve()
    matrix = root / MATRIX_REL
    errors = []
    warnings = []
    if not root.is_dir():
        return {"version": SKILL_VERSION, "root": str(root), "ok": False,
                "input_error": True, "errors": ["技能根目录不存在或不是目录"], "warnings": [], "rows": []}
    if not matrix.is_file():
        return {"version": SKILL_VERSION, "root": str(root), "ok": False,
                "input_error": True, "errors": [f"缺少 {MATRIX_REL.as_posix()}"], "warnings": [], "rows": []}

    try:
        text = matrix.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"version": SKILL_VERSION, "root": str(root), "ok": False,
                "input_error": True, "errors": [f"无法读取评测矩阵：{exc}"], "warnings": [], "rows": []}

    rows = parse_rows(text)
    ids = [row["id"] for row in rows]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    missing = [item for item in EXPECTED_IDS if item not in ids]
    extra = [item for item in ids if item not in EXPECTED_IDS]
    if missing:
        errors.append(f"缺少场景：{', '.join(missing)}")
    if extra:
        errors.append(f"存在未登记场景：{', '.join(extra)}")
    if duplicates:
        errors.append(f"场景 ID 重复：{', '.join(duplicates)}")
    if len(rows) != len(EXPECTED_IDS):
        errors.append(f"场景数量为 {len(rows)}，预期 {len(EXPECTED_IDS)}")
    for row in rows:
        for field in ("request", "route", "allowed", "boundary"):
            if not row[field]:
                errors.append(f"{row['id']} 缺少字段：{field}")

    for phrase in ("主路由正确", "权限正确", "停靠正确", "回执完整"):
        if phrase not in text:
            errors.append(f"评测标准缺少：{phrase}")
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").is_file() else ""
    if "评测场景.md" not in skill_text:
        errors.append("SKILL.md 未接入评测场景矩阵")
    if f"v{SKILL_VERSION}" not in text:
        warnings.append(f"评测矩阵未标记当前版本 v{SKILL_VERSION}")

    return {
        "version": SKILL_VERSION,
        "root": str(root),
        "ok": not errors,
        "input_error": False,
        "errors": errors,
        "warnings": warnings,
        "rows": rows,
        "count": len(rows),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验网络小说创作技能的本地评测场景矩阵")
    parser.add_argument("root", nargs="?", default=str(ROOT), help="技能包根目录")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    report = audit(Path(args.root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"网络小说创作技能 v{report['version']} 评测矩阵")
        print(f"场景数量：{report.get('count', 0)}")
        for error in report["errors"]:
            print(f"[✗] {error}")
        for warning in report["warnings"]:
            print(f"[!] {warning}")
        print("[✓] 评测矩阵通过" if report["ok"] else "[✗] 评测矩阵需要修复")
    if report.get("input_error"):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
