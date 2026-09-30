# -*- coding: utf-8 -*-
"""v7.39 hardening 回归测试。"""
import json
import py_compile
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

class TestV739Hardening(unittest.TestCase):
    def test_modified_python_files_compile(self):
        for rel in ("tools/canonical_parser.py", "tools/full_review.py", "tools/grep_consistency.py", "tools/repair_orchestrator.py", "tools/chapter_readiness.py", "tools/fix_said_tags.py", "tools/release_check.py", "tools/lint_skill.py"):
            py_compile.compile(str(ROOT / rel), doraise=True)

    def test_canonical_role_parser(self):
        parser = load_mod("canonical_parser")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "角色状态快照.md"
            path.write_text("# 角色状态快照\n\n## 李四\n- 状态：已亡\n- 最后出场：第12章\n- 别名：小李、阿四\n", encoding="utf-8")
            data = parser.parse_role_snapshot(path)
            self.assertEqual(data["李四"]["最后出场"], "第12章")
            self.assertEqual(data["李四"]["别名"], "小李、阿四")

    def test_canonical_parser_legacy_role_table(self):
        parser = load_mod("canonical_parser")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "角色状态快照.md"
            path.write_text(
                "| 角色 | 别名 | 状态 | 最后出场 |\n"
                "|---|---|---|---|\n"
                "| 张三 | 阿三 | 已亡 | 第12章 |\n",
                encoding="utf-8")
            data = parser.parse_role_snapshot(path)
            self.assertEqual(data["张三"]["状态"], "已亡")
            self.assertEqual(data["张三"]["最后出场"], "第12章")
            self.assertEqual(data["张三"]["别名"], "阿三")

    def test_repair_runner_accepts_prior_738_queue(self):
        rr = load_mod("repair_runner")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mind").mkdir()
            queue = root / "mind" / "全文审稿队列.json"
            issue = {
                "issue_id":"FR-01-001","level":"P2","cat":"单章","loc":"第1章","msg":"x",
                "evidence":"e","recommended_action":"a","repair_scope":"s","forbidden_action":"f","status":"open"
            }
            queue.write_text(json.dumps({"version":"7.38","issues":[issue]}, ensure_ascii=False), encoding="utf-8")
            _, doc = rr.load_queue(root)
            self.assertEqual(doc["version"], "7.38")
            self.assertEqual(rr.set_status(root, "FR-01-001", "fixed"), 0)
            saved = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], "7.39")
            self.assertEqual(saved["issues"][0]["status"], "fixed")

    def test_mechanical_issue_routes_to_scoped_repair(self):
        ro = load_mod("repair_orchestrator")
        self.assertEqual(ro.classify({"msg":"机械问题：光杆说引导 6 次"}), "mechanical_candidate")

    def test_full_review_mixed_buffer_streak(self):
        fr = load_mod("full_review")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mind").mkdir()
            (root / "书稿").mkdir()
            for n in range(1, 5):
                (root / "书稿" / f"第{n:03d}章_测试.md").write_text(f"第{n}章 测试\n\n正文。\n", encoding="utf-8")
            (root / "mind" / "章节目录.md").write_text("| 章号 | 节奏类型 |\n|---|---|\n| 1 | 缓冲-对话 |\n| 2 | 缓冲-线索 |\n| 3 | 缓冲-代价 |\n| 4 | 缓冲-对话 |\n", encoding="utf-8")
            review = fr.Review(root)
            review.scan_rhythm(root, [])
            self.assertTrue(any("缓冲型节奏合计连续 4 章" in item["msg"] for item in review.issues))

    def test_grep_limit_zero_has_zero_history(self):
        gc = load_mod("grep_consistency")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "书稿").mkdir()
            (root / "mind").mkdir()
            for n in (1, 2, 3):
                (root / "书稿" / f"第{n}章_测试.md").write_text("正文。\n", encoding="utf-8")
            (root / "mind" / "角色状态快照.md").write_text("## 李四\n- 状态：重伤\n", encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                gc.scan(str(root), 0)
            self.assertIn("B 类扫描范围：0 章", out.getvalue())

    def test_repair_cycle_without_apply_is_non_mutating(self):
        ro = load_mod("repair_orchestrator")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mind").mkdir()
            (root / "书稿").mkdir()
            chapter = root / "书稿" / "第001章_测试.md"
            chapter.write_text("第1章 测试\n\n他说：“你好。”\n", encoding="utf-8")
            (root / "mind" / "全文审稿队列.json").write_text(json.dumps({"round": 1, "issues": [{"level": "P2", "cat": "单章", "loc": "第1章", "msg": "他说：引导过多"}]}, ensure_ascii=False), encoding="utf-8")
            before = chapter.read_text(encoding="utf-8")
            rc = ro.main([str(root), "cycle", "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(chapter.read_text(encoding="utf-8"), before)


    def test_wont_fix_is_never_executable(self):
        ro = load_mod("repair_orchestrator")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mind").mkdir()
            (root / "书稿").mkdir()
            (root / "书稿" / "第001章_测试.md").write_text("第1章 测试\n\n他说：“你好。”\n", encoding="utf-8")
            queue = root / "mind" / "全文审稿队列.json"
            queue.write_text(json.dumps({"round": 1, "issues": [{
                "issue_id":"FR-01-001","level":"P2","cat":"单章","loc":"第1章",
                "msg":"机械问题：光杆说引导","evidence":"e","recommended_action":"a",
                "repair_scope":"s","forbidden_action":"f","status":"wont_fix"
            }]}, ensure_ascii=False), encoding="utf-8")
            ro.prepare(root)
            self.assertEqual(ro.resolve_targets(root), [])

    def test_repair_plan_rejects_changed_queue(self):
        ro = load_mod("repair_orchestrator")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mind").mkdir()
            (root / "书稿").mkdir()
            queue = root / "mind" / "全文审稿队列.json"
            queue.write_text(json.dumps({"round": 1, "issues": []}, ensure_ascii=False), encoding="utf-8")
            ro.prepare(root)
            queue.write_text(json.dumps({"round": 2, "issues": []}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                ro.resolve_targets(root)

    def test_semantic_gate_accepts_complete_evidence(self):
        cr = load_mod("chapter_readiness")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "书稿").mkdir()
            (root / "mind" / "审校").mkdir(parents=True)
            (root / "书稿" / "第001章_测试.md").write_text("第1章 测试\n\n正文。\n", encoding="utf-8")
            checks = {str(i): {"status": "pass", "evidence": f"证据{i}", "location": f"第{i}项"} for i in range(14, 31)}
            import hashlib
            digest = hashlib.sha256((root / "书稿" / "第001章_测试.md").read_bytes()).hexdigest()
            (root / "mind" / "审校" / "第001章审校.json").write_text(
                json.dumps({"version": "7.39", "chapter": 1, "chapter_sha256": digest, "checks": checks}, ensure_ascii=False),
                encoding="utf-8")
            result = cr.semantic_gate(root, 1)
            self.assertTrue(result["ok"])
            (root / "书稿" / "第001章_测试.md").write_text("第1章 测试\n\n正文变更。\n", encoding="utf-8")
            stale = cr.semantic_gate(root, 1)
            self.assertFalse(stale["ok"])
            self.assertIn("chapter_sha256", " ".join(stale["tail"]))

if __name__ == "__main__":
    unittest.main(verbosity=1)
