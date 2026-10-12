# -*- coding: utf-8 -*-
"""v7.44 回归测试：主文件瘦身、审校骨架生成器、语义弱证据档、规则观察期到期。

钉住四件事：
  1. SKILL.md 退回「路由中枢」定位，不再与 references/写作铁律.md 重复；
  2. review_skeleton.py 生成的骨架覆盖第14-30项且默认不会误通过 Gate；
  3. weak 弱证据档让 Gate 不卡死，但绝不给出正式交付结论；
  4. 候选/实验态规则不能无限期挂着，lint 会点名。
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import config  # noqa: E402


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review_skeleton = load_mod("review_skeleton")
chapter_readiness = load_mod("chapter_readiness")
doctor = load_mod("doctor")


def make_project(tmp: Path, chapter: int = 1, body: str = "正文内容。\n" * 30) -> Path:
    book = tmp / "书稿"
    book.mkdir(parents=True, exist_ok=True)
    (book / f"第{chapter:03d}章_测试.md").write_text(f"第{chapter}章 测试\n{body}", encoding="utf-8")
    (tmp / "mind").mkdir(exist_ok=True)
    return tmp


class TestSlimSkill(unittest.TestCase):
    def test_skill_md_size_budget(self):
        size = (ROOT / "SKILL.md").stat().st_size
        self.assertLessEqual(size, 50 * 1024, f"SKILL.md 已回涨到 {size} 字节，超过 50KB 预算")

    def test_skill_keeps_router_essentials(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for anchor in ("模式路由表", "失败码与交付闸门", "写章节执行流程", "## 📚 版本历史"):
            self.assertIn(anchor, skill, f"瘦身把路由中枢必需段落删掉了：{anchor}")
        self.assertIn(f"v{config.SKILL_VERSION}", skill.split("## 📚 版本历史", 1)[0])

    def test_writing_rules_not_duplicated(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        # 写作铁律正文只保留在 reference 手册里
        self.assertIn("references/写作铁律.md", skill)
        for moved in ("黄金开篇铁律", "三种章末断点", "番茄爆款铁律"):
            self.assertNotIn(f"## {moved}", skill, f"{moved} 仍整段留在主文件")
        self.assertTrue((ROOT / "references" / "写作铁律.md").is_file())

    def test_extracted_manuals_exist(self):
        for rel in ("references/目录结构.md", "references/指令速查.md", "references/30项校验明细.md"):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_doctor_reads_tree_from_external_doc(self):
        tree_doc = doctor.load_tree_doc(ROOT)
        self.assertIn("技能目录结构", tree_doc)
        registered, exempt = doctor.parse_skill_tree(tree_doc)
        self.assertGreaterEqual(len(registered), 80)
        self.assertIn("references/目录结构.md", registered)
        self.assertTrue(exempt)


class TestReviewSkeleton(unittest.TestCase):
    def test_names_come_from_core_map(self):
        names = review_skeleton.load_check_names()
        for num in range(14, 31):
            self.assertIn(num, names, f"核心校验映射缺少第{num}项名称")
        self.assertIsInstance(names[30], str)

    def test_skeleton_covers_14_to_30_and_defaults_to_revise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            path = root / "书稿" / "第001章_测试.md"
            data = review_skeleton.build_skeleton(root, 1, path, "revise")
            self.assertEqual(sorted(int(k) for k in data["checks"]), list(range(14, 31)))
            for item in data["checks"].values():
                self.assertEqual(item["status"], "revise")
                self.assertTrue(item["evidence"].strip())
            self.assertEqual(data["chapter"], 1)
            self.assertEqual(len(data["chapter_sha256"]), 64)
            # 默认 revise 的骨架必须被交付 Gate 拦下
            self.assertIn("revise", {i["status"] for i in data["checks"].values()})

    def test_cli_generates_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self.assertEqual(review_skeleton.main([str(root), "1"]), 0)
            out = root / "mind" / "审校" / "第001章审校.json"
            self.assertTrue(out.is_file())
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["chapter"], 1)
            self.assertEqual(review_skeleton.main([str(root), "1"]), 1)

    def test_weak_status_skeleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self.assertEqual(review_skeleton.main([str(root), "1", "--status", "weak", "--force"]), 0)
            saved = json.loads((root / "mind" / "审校" / "第001章审校.json").read_text(encoding="utf-8"))
            self.assertTrue(all(i["status"] == "weak" for i in saved["checks"].values()))


class TestWeakEvidence(unittest.TestCase):
    def _write_review(self, root: Path, chapter: int, status_map: dict) -> None:
        import hashlib
        path = root / "书稿" / f"第{chapter:03d}章_测试.md"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checks = {}
        for num in range(14, 31):
            status = status_map.get(num, "pass")
            checks[str(num)] = {"status": status, "evidence": f"第{num}项证据"}
        record = {"version": config.SKILL_VERSION, "chapter": chapter,
                  "chapter_sha256": digest, "checks": checks}
        target = root / "mind" / "审校" / f"第{chapter:03d}章审校.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    def test_weak_gate_does_not_block_but_not_delivery_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self._write_review(root, 1, {14: "weak", 15: "weak"})
            gate = chapter_readiness.semantic_gate(root, 1)
            self.assertTrue(gate["ok"], "weak 档不该卡死 Gate")
            self.assertEqual(gate.get("weak"), [14, 15])

    def test_full_evidence_is_delivery_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self._write_review(root, 1, {})
            gate = chapter_readiness.semantic_gate(root, 1)
            self.assertTrue(gate["ok"])
            self.assertNotIn("weak", gate)

    def test_revise_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self._write_review(root, 1, {20: "revise"})
            gate = chapter_readiness.semantic_gate(root, 1)
            self.assertFalse(gate["ok"])

    def test_status_vocabulary_includes_weak(self):
        self.assertIn("weak", chapter_readiness.VALID_SEMANTIC_STATUS)


class TestObservationExpiry(unittest.TestCase):
    def test_lint_reports_no_expired_observation(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tools" / "lint_skill.py")],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout[-1200:])
        self.assertNotIn("规则观察期到期", proc.stdout,
                         "有候选/实验态规则超过 3 个版本未裁定，须做升稳定/修正/废弃/延长四选一")

    def test_retired_entry_kept_in_ledger(self):
        ledger = (ROOT / "references" / "规则台账.md").read_text(encoding="utf-8")
        self.assertIn("| RB-027 |", ledger)
        self.assertIn("废弃", ledger)


if __name__ == "__main__":
    unittest.main(verbosity=1)
