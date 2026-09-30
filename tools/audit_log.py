# -*- coding: utf-8 -*-
"""小说项目追加式审计日志（v7.37）。

默认写入 <项目>/.story-review/audit.jsonl。日志采用 SHA-256 链，可验证是否被篡改。
只记录工具动作、对象、状态和证据摘要，不记录正文内容。
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from config import SKILL_VERSION

LOG_REL = Path(".story-review") / "audit.jsonl"

def _canonical(item: dict) -> bytes:
    payload = {k: v for k, v in item.items() if k != "hash"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _read_lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"审计日志第{no}行 JSON 无法解析：{exc}") from exc
    return rows

def append_event(root: Path, event: str, subject: str = "", status: str = "", details: dict | None = None) -> dict:
    root = Path(root).expanduser().resolve()
    path = root / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_lines(path)
    previous_hash = rows[-1].get("hash", "") if rows else ""
    item = {"version": SKILL_VERSION, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "event": event, "subject": subject, "status": status, "details": details or {}, "previous_hash": previous_hash}
    item["hash"] = hashlib.sha256(_canonical(item)).hexdigest()
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    return item

def verify_log(root: Path) -> dict:
    root = Path(root).expanduser().resolve()
    path = root / LOG_REL
    rows = _read_lines(path)
    previous_hash = ""
    errors = []
    for index, item in enumerate(rows, 1):
        if item.get("previous_hash", "") != previous_hash:
            errors.append(f"第{index}条 previous_hash 不匹配")
        expected = hashlib.sha256(_canonical(item)).hexdigest()
        if item.get("hash") != expected:
            errors.append(f"第{index}条 hash 不匹配")
        previous_hash = item.get("hash", "")
    return {"version": SKILL_VERSION, "path": str(path), "count": len(rows), "ok": not errors, "errors": errors}

def main(argv=None):
    ap = argparse.ArgumentParser(description=f"小说项目追加式审计日志 v{SKILL_VERSION}")
    sub = ap.add_subparsers(dest="command", required=True)
    add = sub.add_parser("append"); add.add_argument("project"); add.add_argument("--event", required=True); add.add_argument("--subject", default=""); add.add_argument("--status", default=""); add.add_argument("--details", default="{}")
    ver = sub.add_parser("verify"); ver.add_argument("project"); ver.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.command == "append":
            item = append_event(Path(args.project), args.event, args.subject, args.status, json.loads(args.details))
            print(json.dumps(item, ensure_ascii=False, indent=2)); return 0
        report = verify_log(Path(args.project))
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"审计日志：{report['count']} 条；{'完整' if report['ok'] else '存在篡改/损坏'}")
        for error in report["errors"]: print(f"[✗] {error}")
        return 0 if report["ok"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[✗] 审计日志操作失败：{exc}"); return 2

if __name__ == "__main__":
    raise SystemExit(main())
