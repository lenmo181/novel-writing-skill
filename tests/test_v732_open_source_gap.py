# -*- coding: utf-8 -*-
"""v7.32 开源差距补齐回归测试。"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


init_project = load_mod("init_project")
entity_index = load_mod("entity_index")
project_health = load_mod("project_health")
project_audit = load_mod("project_audit")
research_audit = load_mod("research_audit")


class TestV732OpenSourceGap(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novel_v732_")
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.root = Path(self.temp_dir) / "雾城拾荒者"

    def test_init_is_complete_idempotent_and_preserves_existing_files(self):
        first = init_project.init_project(
            self.root, "雾城拾荒者", "都市悬疑", "番茄", "80万字"
        )
        self.assertEqual(first["file_count"], 20)
        self.assertEqual(len(first["created"]), 20)
        readme = self.root / "README.md"
        readme.write_text("# 作者已确认内容\n", encoding="utf-8")
        second = init_project.init_project(
            self.root, "雾城拾荒者", "都市悬疑", "番茄", "80万字"
        )
        self.assertIn("README.md", second["skipped"])
        self.assertEqual(readme.read_text(encoding="utf-8"), "# 作者已确认内容\n")
        self.assertTrue((self.root / "mind/章节目录.md").is_file())
        self.assertTrue((self.root / ".story-review/state.md").is_file())

    def test_health_aggregates_structure_and_entity_issues(self):
        init_project.init_project(self.root, "雾城拾荒者")
        (self.root / "设定/角色.md").write_text(
            "# 角色设定\n\n"
            "## 林舟\n\n- 别名：小林\n- 关系：与苏晚合作\n\n"
            "## 苏晚\n\n- 别名：小林\n- 关系：与林舟合作\n",
            encoding="utf-8",
        )
        (self.root / "mind/角色状态快照.md").write_text(
            "# 角色状态快照\n\n"
            "## 林舟\n\n- 首次出场章：第1章\n- 状态：受伤\n- 最后出场：第2章\n\n"
            "## 苏晚\n\n- 首次出场章：第1章\n- 状态：清醒\n- 最后出场：第2章\n",
            encoding="utf-8",
        )
        for number in (1, 3):
            (self.root / "书稿" / f"第{number:03d}章_试探.md").write_text(
                f"第{number}章 试探\n\n林舟和小林继续前进。\n", encoding="utf-8"
            )
        report = project_health.health(self.root)
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("CHAPTER_GAP", codes)
        self.assertIn("DUPLICATE_ALIAS", codes)
        self.assertEqual(report["stats"]["chapter_count"], 2)
        self.assertEqual(report["stats"]["entity_count"], 2)

    def test_entity_index_counts_non_overlapping_aliases_and_relations(self):
        init_project.init_project(self.root, "测试书")
        (self.root / "设定/角色.md").write_text(
            "# 角色设定\n\n"
            "## 林舟\n\n- 别名：小林\n- 关系：与苏晚合作\n\n"
            "## 苏晚\n\n- 别名：晚晚\n- 关系：与林舟合作\n",
            encoding="utf-8",
        )
        (self.root / "mind/角色状态快照.md").write_text(
            "# 角色状态快照\n\n## 林舟\n\n- 状态：正常\n\n"
            "## 苏晚\n\n- 状态：正常\n", encoding="utf-8"
        )
        for number, body in ((1, "林舟叫小林。"), (2, "小林等苏晚。")):
            (self.root / "书稿" / f"第{number:03d}章_试.md").write_text(
                f"第{number}章 试\n\n{body}\n", encoding="utf-8"
            )
        report = entity_index.build_index(self.root)
        lin = next(item for item in report["entities"] if item["name"] == "林舟")
        self.assertEqual(lin["first_mention"], 1)
        self.assertEqual(lin["last_mention"], 2)
        self.assertEqual(lin["mention_count"], 3)
        self.assertTrue(any(item["value"] == "与苏晚合作" for item in lin["relations"]))
        rendered = entity_index.render(report)
        self.assertIn("graph LR", rendered)
        self.assertIn("林舟", rendered)

    def test_research_audit_flags_ledger_issues(self):
        init_project.init_project(self.root, "测试书")
        ledger = self.root / "研究" / "来源台账.md"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            "# 来源台账\n\n"
            "| 编号 | 来源名称 | 类型 | 链接/文件路径 | 访问日期 | 用途 | 可用事实 | 待核问题 | 状态 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| R-001 | 明代军制考 | 书目 | 设定/资料/军制.md | 2026-09-29 | 军制 | 卫所制 | - | 已核 |\n"
            "| R-001 | 重复来源 | 网页 | https://example.com | 2026-09-29 | 重复 | - | - | 待核 |\n"
            "| [待补充] | [待补充] | 网页 | [待补充] | 2026-09-29 | - | - | 疑点 | 不明 |\n"
            "| R-003 | 已核带疑点 | 网页 | https://example.com/x | 2026-09-29 | - | - | 未解决 | 已核 |\n",
            encoding="utf-8",
        )
        report = research_audit.audit(ledger, self.root)
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("SOURCE_ID_DUPLICATE", codes)
        self.assertIn("SOURCE_ID_MISSING", codes)
        self.assertIn("SOURCE_NAME_MISSING", codes)
        self.assertIn("SOURCE_LOCATION_MISSING", codes)
        self.assertIn("SOURCE_STATUS_INVALID", codes)
        self.assertIn("SOURCE_UNRESOLVED_NOTE", codes)
        self.assertIn("SOURCE_PATH_UNRESOLVED", codes)
        self.assertEqual(report["row_count"], 4)
        self.assertEqual(report["pending_count"], 1)
        rendered = research_audit.render(report)
        self.assertIn("研究来源台账检查", rendered)
        self.assertIn("SOURCE_ID_DUPLICATE", rendered)

    def test_research_audit_missing_ledger_exit_code(self):
        result = subprocess.run(
            [sys.executable, str(TOOLS / "research_audit.py"), str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["issues"][0]["code"], "LEDGER_MISSING")
        self.assertEqual(payload["row_count"], 0)

    def test_cli_help_and_json_output(self):
        for tool in ("init_project.py", "entity_index.py", "project_health.py", "research_audit.py"):
            result = subprocess.run(
                [sys.executable, str(TOOLS / tool), "--help"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        init_project.init_project(self.root, "测试书")
        result = subprocess.run(
            [sys.executable, str(TOOLS / "project_health.py"), str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["version"], project_health.SKILL_VERSION)


if __name__ == "__main__":
    unittest.main()
