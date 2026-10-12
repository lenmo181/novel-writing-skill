# -*- coding: utf-8 -*-
"""
v7.41 回归测试：墨尺一键安装向导 + 持久化路径兜底 + 对话三症状机械线索钉住
运行：python -m unittest discover -s tests -p "test_*.py"
覆盖：
  mochi_setup —— is_ruler_dir 有效性、save/load 往返与坏文件容错、
                 resolve_ruler_dir 优先级（--dir > 环境变量 > 持久化文件 > 默认目录；
                 坏环境变量打印警告但不中断查找）
  mochi_check.ensure_server —— 未安装墨尺时给一键安装指引（立即返回不打桩不等待）、
                 有持久化路径时按其拉起（launch_server 打桩）、服务已在则不重复拉起
  check_chapter.dialogue_symptom_checks —— 三症状机械线索在合成文本上出警告
                 （RB-031 观察态：机械线索只出警告，判定权在第20项 AI 语义复核）
"""
import importlib.util
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


setup = load_mod("mochi_setup")
chk = load_mod("check_chapter")
mochi = load_mod("mochi_check")  # 其内部 from mochi_setup import 命中上面注册的模块实例


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._path_file_patcher = mock.patch.object(setup, "PATH_FILE",
                                                    self.tmp / "path.json")
        self._path_file_patcher.start()
        self.addCleanup(self._path_file_patcher.stop)

    def make_ruler(self, name="ruler-a"):
        d = self.tmp / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "server.py").write_text("# fake server\n", encoding="utf-8")
        return d


class TestRulerDirValidity(TempCase):
    def test_valid_dir_has_server_py(self):
        d = self.make_ruler()
        self.assertTrue(setup.is_ruler_dir(d))

    def test_dir_without_server_py_invalid(self):
        d = self.tmp / "empty"
        d.mkdir()
        self.assertFalse(setup.is_ruler_dir(d))

    def test_missing_and_file_paths_invalid(self):
        self.assertFalse(setup.is_ruler_dir(self.tmp / "nope"))
        f = self.tmp / "afile.txt"
        f.write_text("x", encoding="utf-8")
        self.assertFalse(setup.is_ruler_dir(f))


class TestPathPersistence(TempCase):
    def test_save_load_roundtrip(self):
        d = self.make_ruler()
        setup.save_dir(str(d))
        self.assertEqual(setup.load_saved_dir(), str(d))

    def test_missing_file_returns_empty(self):
        self.assertEqual(setup.load_saved_dir(), "")

    def test_corrupted_file_returns_empty(self):
        setup.PATH_FILE.write_text("{not json", encoding="utf-8")
        self.assertEqual(setup.load_saved_dir(), "")


class TestResolvePriority(TempCase):
    def test_explicit_dir_wins(self):
        a, b = self.make_ruler("a"), self.make_ruler("b")
        with mock.patch.dict(os.environ, {setup.KEY_ENV_DIR: str(b)}):
            self.assertEqual(setup.resolve_ruler_dir(str(a)), str(a))

    def test_env_wins_over_persisted(self):
        a, b = self.make_ruler("a"), self.make_ruler("b")
        setup.save_dir(str(a))
        with mock.patch.dict(os.environ, {setup.KEY_ENV_DIR: str(b)}):
            self.assertEqual(setup.resolve_ruler_dir(""), str(b))

    def test_persisted_used_when_env_absent(self):
        a = self.make_ruler("a")
        setup.save_dir(str(a))
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(setup.KEY_ENV_DIR, None)
            self.assertEqual(setup.resolve_ruler_dir(""), str(a))

    def test_invalid_env_warns_and_falls_through(self):
        a = self.make_ruler("a")
        setup.save_dir(str(a))
        bogus = str(self.tmp / "bogus")
        with mock.patch.dict(os.environ, {setup.KEY_ENV_DIR: bogus}):
            self.assertEqual(setup.resolve_ruler_dir(""), str(a))

    def test_default_home_dir_found(self):
        default_dir = self.tmp / ".mochi-ruler"
        default_dir.mkdir(parents=True, exist_ok=True)
        (default_dir / "server.py").write_text("# s\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(setup.KEY_ENV_DIR, None)
            with mock.patch.object(setup.Path, "home", return_value=self.tmp):
                self.assertEqual(setup.resolve_ruler_dir(""), str(default_dir))

    def test_nothing_found_returns_empty(self):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(setup.KEY_ENV_DIR, None)
            with mock.patch.object(setup.Path, "home", return_value=self.tmp):
                self.assertEqual(setup.resolve_ruler_dir(""), "")


class TestEnsureServerFallback(TempCase):
    # 本机 8765 可能常驻真实墨尺服务（向导拉起后不退出）：统一打桩探活=服务不在，
    # 保证测试走「解析墨尺路径」分支而非「服务已在」短路。
    def service_down(self):
        patcher = mock.patch.object(mochi.urllib.request, "urlopen",
                                    side_effect=urllib.error.URLError("down"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_uninstalled_message_points_to_wizard(self):
        self.service_down()
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(setup.KEY_ENV_DIR, None)
            msg = mochi.ensure_server("http://127.0.0.1:8765")
        self.assertIn("mochi_setup.py", msg)
        self.assertIn(setup.KEY_ENV_DIR, msg)  # 仍保留环境变量兜底指引

    def test_persisted_dir_is_launched(self):
        self.service_down()
        d = self.make_ruler("persisted")
        setup.save_dir(str(d))
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(setup.KEY_ENV_DIR, None)
            with mock.patch.object(mochi, "launch_server") as launch, \
                 mock.patch.object(mochi.time, "sleep"):
                msg = mochi.ensure_server("http://127.0.0.1:8765", timeout=0)
        launch.assert_called_once_with(str(d), 8765)
        self.assertIn("超时", msg)  # timeout=0 且服务不在 → 超时文案（打桩下立即返回）

    def test_alive_service_not_relaunched(self):
        err = urllib.error.HTTPError("http://127.0.0.1:8765/", 404, "nf", {}, None)
        with mock.patch.object(mochi.urllib.request, "urlopen", side_effect=err), \
             mock.patch.object(mochi, "launch_server") as launch:
            self.assertIsNone(mochi.ensure_server("http://127.0.0.1:8765"))
        launch.assert_not_called()


class TestVerifyInstallContract(TempCase):
    """verify_install 的回包校验契约必须与 mochi_check 一致（chapters[0].score.total）。"""

    @staticmethod
    def _fake_urlopen(payload):
        import io

        class FakeResp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return FakeResp(payload)

    def test_valid_payload_passes(self):
        import json
        payload = json.dumps({"chapters": [{"score": {"total": 8.8, "real": 8.0,
                                                      "human": 9.0, "imm": 9.0,
                                                      "rhy": 8.0, "syn": 9.0}}]}).encode("utf-8")
        with mock.patch.object(setup.urllib.request, "urlopen",
                               return_value=self._fake_urlopen(payload)):
            self.assertEqual(setup.verify_install(str(self.tmp), "http://127.0.0.1:8765"), "")

    def test_missing_score_total_reports_error(self):
        import json
        payload = json.dumps({"chapters": [{"score": {"real": 8.0}}]}).encode("utf-8")
        with mock.patch.object(setup.urllib.request, "urlopen",
                               return_value=self._fake_urlopen(payload)):
            msg = setup.verify_install(str(self.tmp), "http://127.0.0.1:8765")
        self.assertIn("score.total", msg)

    def test_missing_chapters_reports_error(self):
        import json
        payload = json.dumps({"name": "x", "summary": {"chapters": 1}}).encode("utf-8")
        with mock.patch.object(setup.urllib.request, "urlopen",
                               return_value=self._fake_urlopen(payload)):
            msg = setup.verify_install(str(self.tmp), "http://127.0.0.1:8765")
        self.assertIn("缺 chapters", msg)


class TestDialogueSymptomClues(TempCase):
    span_re = chk.dialogue_span_re("any")

    def test_symptom1_symmetric_dialogue_run(self):
        para = "“今天山下镇口的粥棚又排出去半里地，说是官府放的粮。”"
        body = "\n".join([para] * 5)
        lines, _ = chk.body_lines(body)
        warnings = []
        chk.dialogue_symptom_checks(body, lines, self.span_re, warnings)
        self.assertTrue(any("机械问答对称" in w for w in warnings))

    def test_symptom2_lecture_in_long_dialogue(self):
        lecture = ("“所谓宗门等级，是指山门内外的尊卑之分，分为外门、内门与真传三层，"
                   "共有弟子三千余人，位于大陆东侧的云州地界，历年招收弟子自有律法规矩。”")
        body = "他清了清嗓子，摆出讲学的架势。\n" + lecture + "\n台下少年们面面相觑。"
        self.assertGreaterEqual(chk.count_chars(lecture), 60)  # 夹具自证达标
        lines, _ = chk.body_lines(body)
        warnings = []
        chk.dialogue_symptom_checks(body, lines, self.span_re, warnings)
        self.assertTrue(any("科普嘴" in w for w in warnings))

    def test_symptom3_jest_markers(self):
        body = ("“哈哈，这一手可是绝了。”他笑得直不起腰。\n"
                "周围人也跟着起哄。\n"
                "“笑死，这位兄台实在太牛了。”")
        lines, _ = chk.body_lines(body)
        warnings = []
        chk.dialogue_symptom_checks(body, lines, self.span_re, warnings)
        self.assertTrue(any("插科打诨" in w for w in warnings))

    def test_normal_dialogue_no_symptoms(self):
        body = ("“让开。”她只说了两个字。\n"
                "他没让，反而往前站了半步。\n"
                "“你不明白，桥那头死过人，昨夜的事，官府还没结案。”\n"
                "她盯着他看了很久，转身走了。")
        lines, _ = chk.body_lines(body)
        warnings = []
        chk.dialogue_symptom_checks(body, lines, self.span_re, warnings)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
