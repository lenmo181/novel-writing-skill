"""v7.52 章节任务卡与场景连续性专项回归。"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


brief = load_mod("chapter_brief")
scene = load_mod("scene_continuity")


class ContinuityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="novel_v752_continuity_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for rel in ("书稿", "大纲", "设定", "mind/回顾"):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        (self.root / "大纲/章纲.md").write_text(
            "| 章号 | 章节名 | 节奏类型 | 本章目标 | 冲突/代价 | 章末钩子类型与指纹 | 伏笔编号 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 2 | 门后 | 主线 | 找到密信 | 门卫索要代价 | 主角-发现-密信 | F-01 |\n",
            encoding="utf-8",
        )
        (self.root / "大纲/卷纲.md").write_text(
            "| 卷号 | 卷名 | 起止章 | 本卷目标 | 核心冲突 | 卷内里程碑 | 卷末钩子/变化 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 1 | 起局 | 1-3 | 查清密信 | 门卫封锁 | 20%/50%/80% | 门后有人 |\n",
            encoding="utf-8",
        )
        (self.root / "大纲/场景纲.md").write_text(self.scene_text(), encoding="utf-8")
        (self.root / "mind/时间线.md").write_text(
            "| 章节 | 故事内时间 | 跨度说明 | 读者已知变化 |\n|---|---|---|---|\n"
            "| 第2章 | 第1天10点 | 接上章 | 密信出现 |\n", encoding="utf-8")
        (self.root / "mind/角色状态快照.md").write_text(
            "## 林舟\n\n- 别名：无\n- 首次出场章：第1章\n- 位置：旧仓库\n- 持有：铜钥匙\n- 状态：正常\n- 情绪：警惕\n- 知情：只知道密信存在\n- 最后出场：第2章\n", encoding="utf-8")
        (self.root / "mind/伏笔追踪表.md").write_text(
            "| 编号 | 伏笔内容 | 埋设章 | 预计回收章 | Tier | 状态 |\n|---|---|---|---|---|---|\n"
            "| F-01 | 密信来源 | 第1章 | 第4章 | T2 | 未回收 |\n", encoding="utf-8")
        (self.root / "mind/剧情走向锁定.md").write_text("| 日期 | 决策内容 | 来源（用户指定/正文已写死） |\n|---|---|---|\n", encoding="utf-8")
        (self.root / "书稿/第001章_上章.md").write_text("第1章 上章\n\n林舟在仓库门口捡到一枚铜钥匙。", encoding="utf-8")
        (self.root / "mind/回顾/第001章回顾.md").write_text(
            "## 第001章回顾\n- 关键事件：林舟捡到铜钥匙。\n- 下章承接：去旧仓库开门。\n", encoding="utf-8")

    def scene_text(self):
        return (
            "| 章号 | 场景 | 视角 | 地点/时间 | 在场人物 | 进入原因 | 承接事件 | 目标 | 阻碍 | 转折/不可逆变化 | 下一场过渡 | 离开钩子 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| 2 | 1 | 林舟 | 旧仓库/第1天10点 | 林舟 | 接上章捡到钥匙 | 铜钥匙在手 | 开门 | 门卫拦截 | 门卫提出代价 | 林舟交出铜钥匙 | 门开了一条缝 |\n"
            "| 2 | 2 | 林舟 | 旧仓库内/第1天10点 | 林舟 | 门卫让路 | 门开了一条缝 | 找密信 | 光线不足 | 看见密信 | 回到门口 | 密信在桌上 |\n"
        )

    def write_scene(self, text):
        (self.root / "大纲/场景纲.md").write_text(text, encoding="utf-8")

    def test_c01_location_change_without_transition(self):
        text = self.scene_text().replace(
            "| 2 | 2 | 林舟 | 旧仓库内/第1天10点 | 林舟 | 门卫让路 | 门开了一条缝 | 找密信 | 光线不足 | 看见密信 | 回到门口 | 密信在桌上 |",
            "| 2 | 2 | 林舟 | 城外车站/第1天10点 | 林舟 |  |  | 找密信 | 光线不足 | 看见密信 |  | 密信在桌上 |",
        )
        self.write_scene(text)
        report = scene.check(self.root, 2)
        self.assertIn("SCENE_TRANSITION_MISSING", {item["code"] for item in report["errors"]})

    def test_c02_missing_entry_reason(self):
        self.write_scene(self.scene_text().replace("接上章捡到钥匙", "[待补充]", 1))
        report = scene.check(self.root, 2)
        self.assertTrue(any("进入原因" in item["message"] for item in report["errors"]))

    def test_c03_missing_carry_event(self):
        self.write_scene(self.scene_text().replace("铜钥匙在手", "[待补充]", 1))
        report = scene.check(self.root, 2)
        self.assertTrue(any("承接事件" in item["message"] for item in report["errors"]))

    def test_c04_missing_people(self):
        self.write_scene(self.scene_text().replace("| 林舟 | 接上章", "| [待补充] | 接上章", 1))
        report = scene.check(self.root, 2)
        self.assertTrue(any("在场人物" in item["message"] for item in report["errors"]))

    def test_c05_pov_change_without_boundary(self):
        text = self.scene_text().replace(
            "| 2 | 2 | 林舟 | 旧仓库内/第1天10点 | 林舟 | 门卫让路 | 门开了一条缝 | 找密信 | 光线不足 | 看见密信 | 回到门口 | 密信在桌上 |",
            "| 2 | 2 | 门卫 | 旧仓库内/第1天10点 | 林舟 |  |  | 找密信 | 光线不足 | 看见密信 |  | 密信在桌上 |",
        )
        self.write_scene(text)
        report = scene.check(self.root, 2)
        self.assertIn("SCENE_TRANSITION_MISSING", {item["code"] for item in report["errors"]})

    def test_c06_scene_order(self):
        self.write_scene(self.scene_text().replace("| 2 | 2 |", "| 2 | 1 |", 1))
        report = scene.check(self.root, 2)
        self.assertIn("SCENE_ORDER", {item["code"] for item in report["errors"]})

    def test_c07_dead_role(self):
        snapshot = (self.root / "mind/角色状态快照.md").read_text(encoding="utf-8")
        snapshot += "\n## 门卫\n\n- 状态：已亡\n- 最后出场：第1章\n"
        (self.root / "mind/角色状态快照.md").write_text(snapshot, encoding="utf-8")
        self.write_scene(self.scene_text().replace("林舟 | 接上章", "林舟、门卫 | 接上章", 1))
        report = scene.check(self.root, 2)
        self.assertIn("SCENE_DEAD_ROLE", {item["code"] for item in report["errors"]})

    def test_c08_same_time_double_location(self):
        text = self.scene_text().replace("旧仓库内/第1天10点", "城外车站/第1天10点")
        self.write_scene(text)
        report = scene.check(self.root, 2)
        self.assertIn("SCENE_DOUBLE_LOCATION", {item["code"] for item in report["errors"]})

    def test_c09_legacy_schema_is_explicit_warning(self):
        self.write_scene(
            "| 章号 | 场景 | 视角 | 地点/时间 | 目标 | 阻碍 | 转折/不可逆变化 | 离开钩子 |\n"
            "|---|---|---|---|---|---|---|---|\n| 2 | 1 | 林舟 | 旧仓库/第1天10点 | 开门 | 门卫 | 门开 | 密信 |\n"
        )
        report = scene.check(self.root, 2)
        self.assertTrue(report["ok"])
        self.assertIn("SCENE_SCHEMA_LEGACY", {item["code"] for item in report["warnings"]})

    def test_c10_brief_needs_input_when_goal_missing(self):
        outline = (self.root / "大纲/章纲.md").read_text(encoding="utf-8").replace("找到密信", "[待补充]")
        (self.root / "大纲/章纲.md").write_text(outline, encoding="utf-8")
        card = brief.build_brief(self.root, 2)
        self.assertEqual(card["status"], "needs_input")
        self.assertIn("chapter_goal", card["missing"])

    def test_c11_brief_keeps_previous_fact_and_hash(self):
        card = brief.build_brief(self.root, 2)
        self.assertIn("捡到一枚铜钥匙", card["previous"]["tail"])
        paths = {item["path"] for item in card["sources"]}
        self.assertIn("书稿/第001章_上章.md", paths)
        self.assertTrue(all(item["sha256"] for item in card["sources"]))

    def test_c12_brief_carries_known_information(self):
        card = brief.build_brief(self.root, 2)
        self.assertEqual(card["known_information"]["林舟"], "只知道密信存在")

    def test_c13_brief_preserves_open_foreshadow(self):
        card = brief.build_brief(self.root, 2)
        self.assertEqual(card["foreshadows"][0]["状态"], "未回收")

    def test_c14_brief_write_is_explicit_and_reversible(self):
        card = brief.build_brief(self.root, 2)
        target = brief.write_brief(self.root, card)
        self.assertTrue(target.is_file())
        saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["chapter"], 2)
        self.assertEqual(saved["status"], "ready")

    def test_c15_brief_marks_missing_scene_instead_of_inventing(self):
        (self.root / "大纲/场景纲.md").write_text("", encoding="utf-8")
        card = brief.build_brief(self.root, 2)
        self.assertEqual(card["status"], "needs_input")
        self.assertIn("scene_outline", card["missing"])


if __name__ == "__main__":
    unittest.main()
