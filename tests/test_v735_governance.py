# -*- coding: utf-8 -*-
"""v7.36 治理回归测试：回归状态语义、修复队列状态层、11列规则台账和运行时版本台账。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import full_review  # noqa: E402


class TestRegressionSemantics(unittest.TestCase):
    def test_only_confirmed_fixed_can_regress(self):
        prev = [{"cat": "设定", "loc": "老王", "msg": "复活", "status": "open"}]
        cur = [{"issue_id": "FR-02-001", "cat": "设定", "loc": "老王", "msg": "复活再次出现"}]
        d = full_review.diff_rounds(prev, cur, [])
        self.assertEqual(d["regressed"], [])

        prev[0]["status"] = "fixed"
        d = full_review.diff_rounds(prev, cur, [])
        self.assertEqual(len(d["regressed"]), 1)

    def test_resolved_log_only_accepts_fixed(self):
        cur = [{"issue_id": "FR-03-001", "cat": "设定", "loc": "老王", "msg": "复活再次出现"}]
        open_log = [{"cat": "设定", "loc": "老王", "msg": "旧问题", "prev_status": "open"}]
        fixed_log = [{"cat": "设定", "loc": "赵六", "msg": "旧问题", "prev_status": "fixed"}]
        self.assertEqual(full_review.diff_rounds([], cur, open_log)["regressed"], [])
        cur2 = [{"issue_id": "FR-03-002", "cat": "设定", "loc": "赵六", "msg": "复发"}]
        self.assertEqual(len(full_review.diff_rounds([], cur2, fixed_log)["regressed"]), 1)


class TestRepairRunner(unittest.TestCase):
    def _queue(self, root):
        p = root / "mind" / "全文审稿队列.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({
            "version": "7.38",
            "round": 1,
            "issues": [{
                "issue_id": "FR-01-001", "level": "P1", "cat": "单章", "loc": "第1章",
                "msg": "测试问题", "evidence": "测试", "recommended_action": "人工修复",
                "repair_scope": "病灶段", "forbidden_action": "整章重写", "status": "open"
            }]
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    def test_state_transition_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self._queue(root)
            runner = TOOLS / "repair_runner.py"
            r1 = subprocess.run([sys.executable, str(runner), str(root), "--mark-fixed", "FR-01-001"],
                                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r1.returncode, 0)
            doc = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(doc["issues"][0]["status"], "fixed")
            self.assertTrue(p.with_suffix(".json.bak").is_file())
            r2 = subprocess.run([sys.executable, str(runner), str(root), "--reopen", "FR-01-001"],
                                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r2.returncode, 0)
            doc2 = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(doc2["issues"][0]["status"], "reopened")


class TestGovernanceSchemas(unittest.TestCase):
    def test_ledger_has_30_rows_and_11_fields(self):
        ledger = (ROOT / "references" / "规则台账.md").read_text(encoding="utf-8")
        rows = [x for x in ledger.splitlines() if x.startswith("| RB-")]
        self.assertEqual(len(rows), 30)
        for row in rows:
            cells = row.split("|")[1:-1]
            self.assertEqual(len(cells), 11, row[:80])
        self.assertIn("| RB-028 |", ledger)
        self.assertIn("| RB-029 |", ledger)
        self.assertIn("| RB-030 |", ledger)

    def test_runtime_manifest_covers_all_reference_manuals(self):
        manifest = (ROOT / "references" / "版本台账.md").read_text(encoding="utf-8")
        rows = [x for x in manifest.splitlines() if x.startswith("| references/")]
        actual = {str(p.relative_to(ROOT)) for p in (ROOT / "references").glob("*.md")}
        listed = {x.split("|")[1].strip() for x in rows}
        self.assertEqual(listed, actual)
        self.assertTrue(rows)
        self.assertTrue(all("| v7.38 |" in x for x in rows))


class TestReleaseVersion(unittest.TestCase):
    def test_config_and_skill(self):
        from config import SKILL_VERSION, RELEASE_DATE
        self.assertEqual(SKILL_VERSION, "7.38")
        self.assertEqual(RELEASE_DATE, "2026-09-30")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("v7.38", skill.split("## 📚 版本历史", 1)[0])
        self.assertIn("v7.38", readme.split("## 版本历史", 1)[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
