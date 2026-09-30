# -*- coding: utf-8 -*-
"""全文审稿修复队列状态执行层（v7.38）。

只管理 mind/全文审稿队列.json 的状态，不直接修改正文、档案或大纲。
状态：open / reopened / fixed / auto_fixed / wont_fix。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

VALID_STATUSES = {"open", "reopened", "fixed", "auto_fixed", "wont_fix"}
QUEUE_NAME = "mind/全文审稿队列.json"
REQUIRED_ISSUE_FIELDS = {"issue_id", "level", "cat", "loc", "msg", "evidence", "recommended_action", "repair_scope", "forbidden_action", "status"}


def load_queue(root: Path):
    path = root / QUEUE_NAME
    if not path.is_file():
        raise FileNotFoundError(f"队列不存在：{path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") not in {None, config.SKILL_VERSION}:
        raise ValueError(f"队列版本 {doc.get('version')} 与当前技能 {config.SKILL_VERSION} 不一致")
    for idx, issue in enumerate(doc.get("issues") or [], 1):
        missing = REQUIRED_ISSUE_FIELDS - set(issue)
        if missing:
            raise ValueError(f"队列第{idx}条缺字段：{sorted(missing)}")
        if issue.get("status") not in VALID_STATUSES:
            raise ValueError(f"队列第{idx}条状态非法：{issue.get('status')}")
    return path, doc
def save_queue(path: Path, doc: dict):
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find_issue(doc, issue_id):
    for issue in doc.get("issues") or []:
        if issue.get("issue_id") == issue_id:
            return issue
    return None


def list_issues(doc, as_json=False):
    issues = doc.get("issues") or []
    if as_json:
        print(json.dumps(issues, ensure_ascii=False, indent=1))
        return
    for item in issues:
        print(f"{item.get('issue_id')} | {item.get('status', 'open')} | {item.get('level')} | {item.get('cat')} | {item.get('loc')} | {item.get('msg')}")


def set_status(root: Path, issue_id: str, target: str):
    path, doc = load_queue(root)
    issue = find_issue(doc, issue_id)
    if issue is None:
        print(f"[✗] 找不到 issue_id：{issue_id}")
        return 1
    current = issue.get("status", "open")
    if current not in VALID_STATUSES:
        print(f"[✗] 非法当前状态：{current}")
        return 1
    allowed = {
        "fixed": {"open", "reopened", "wont_fix", "auto_fixed"},
        "auto_fixed": {"open", "reopened", "wont_fix", "fixed"},
        "wont_fix": {"open", "reopened", "fixed", "auto_fixed"},
        "reopened": {"fixed", "auto_fixed", "wont_fix"},
    }
    if target != "open" and current == target:
        print(f"[i] {issue_id} 已是 {target}")
        return 0
    if target == "open":
        allowed_from = {"fixed", "auto_fixed", "wont_fix", "reopened"}
    else:
        allowed_from = allowed.get(target, set())
    if current not in allowed_from:
        print(f"[✗] 不允许状态迁移：{current} → {target}")
        return 1
    issue["status"] = target
    doc.setdefault("meta", {})["last_status_change_utc"] = datetime.now(timezone.utc).isoformat()
    save_queue(path, doc)
    print(f"[✓] {issue_id}: {current} → {target}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="全文审稿修复队列状态管理（不改正文）")
    parser.add_argument("root", help="项目根目录")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出当前队列")
    group.add_argument("--mark-fixed", metavar="ISSUE_ID")
    group.add_argument("--mark-auto-fixed", metavar="ISSUE_ID")
    group.add_argument("--mark-wont-fix", metavar="ISSUE_ID")
    group.add_argument("--reopen", metavar="ISSUE_ID")
    group.add_argument("--open", metavar="ISSUE_ID", help="把已处理项重新打开")
    parser.add_argument("--json", action="store_true", help="列表模式输出 JSON")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.list:
            _, doc = load_queue(root)
            list_issues(doc, args.json)
            return 0
        target_map = {
            "mark_fixed": "fixed",
            "mark_auto_fixed": "auto_fixed",
            "mark_wont_fix": "wont_fix",
            "reopen": "reopened",
            "open": "open",
        }
        for attr, target in target_map.items():
            issue_id = getattr(args, attr)
            if issue_id:
                return set_status(root, issue_id, target)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[✗] 队列读取/写入失败：{e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
