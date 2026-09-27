# -*- coding: utf-8 -*-
"""v7.28 本地评测增强回归测试。"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("doctor", ROOT / "tools" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = doctor
spec.loader.exec_module(doctor)
eval_spec = importlib.util.spec_from_file_location("eval_skill", ROOT / "tools" / "eval_skill.py")
eval_skill = importlib.util.module_from_spec(eval_spec)
sys.modules[eval_spec.name] = eval_skill
eval_spec.loader.exec_module(eval_skill)


class TestV728QualityUpgrade(unittest.TestCase):
    def test_examples_and_doctor_are_routed(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        examples = ROOT / "references" / "操作范例.md"
        cards = ROOT / "references" / "模式操作卡.md"
        matrix = ROOT / "references" / "评测场景.md"
        self.assertTrue(examples.is_file())
        self.assertTrue(cards.is_file())
        self.assertTrue(matrix.is_file())
        for document in (skill, readme):
            self.assertIn("操作范例.md", document)
            self.assertIn("模式操作卡.md", document)
            self.assertIn("doctor.py", document)

    def test_evaluation_matrix_has_sixteen_cases(self):
        matrix = (ROOT / "references" / "评测场景.md").read_text(encoding="utf-8")
        for index in range(1, 17):
            self.assertIn(f"EV-{index:02d}", matrix)
        self.assertIn("主路由正确", matrix)
        self.assertIn("权限正确", matrix)
        self.assertIn("停靠正确", matrix)

    def test_doctor_passes_on_current_package(self):
        report = doctor.audit(ROOT)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["version"], doctor.SKILL_VERSION)  # 动态跟 config，发版不再改测试
        self.assertGreaterEqual(len(report["checks"]), 5)

    def test_runtime_smoke_passes(self):
        results = doctor.runtime_smoke(ROOT, timeout=10)
        failed = [item for item in results if not item["ok"]]
        self.assertFalse(failed, failed)

    def test_package_smoke_passes(self):
        result = doctor.package_smoke(ROOT, timeout=20)
        self.assertTrue(result["ok"], result)

    def test_evaluation_tool_passes(self):
        report = eval_skill.audit(ROOT)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["count"], 16)
        self.assertEqual(len(report["rows"]), 16)
        self.assertTrue(json.dumps(report, ensure_ascii=False))

    def test_receipt_protocol_and_release_check_exist(self):
        protocol = ROOT / "references" / "回执协议.md"
        release_check = ROOT / "tools" / "release_check.py"
        self.assertTrue(protocol.is_file())
        self.assertTrue(release_check.is_file())
        text = protocol.read_text(encoding="utf-8")
        for field in ("状态：", "实际变更：", "校验证据：", "下一步："):
            self.assertIn(field, text)


if __name__ == "__main__":
    unittest.main()
