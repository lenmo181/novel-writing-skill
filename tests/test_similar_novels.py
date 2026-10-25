# -*- coding: utf-8 -*-
"""同类小说研究工具的离线回归测试。"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import similar_novels  # noqa: E402


CARD_HTML = """
<div class="book-list">
<article class="book-card"><a class="book-cover" href="/book/1-a"></a>
<h3><a>雾中来客</a></h3><p class="book-author">作者：甲</p>
<p class="book-summary">山城封锁后，主角发现失踪者留下的密钥，必须在倒计时前查清真相。</p></article>
<article class="book-card"><a class="book-cover" href="/book/2-b"></a>
<h3><a>夜行档案</a></h3><p class="book-author">作者：乙</p>
<p class="book-summary">刑警在旧案中发现新的尸检线索，追查会付出无法挽回的代价。</p></article>
<article class="book-card"><a class="book-cover" href="/book/3-c"></a>
<h3><a>空楼回声</a></h3><p class="book-author">作者：丙</p>
<p class="book-summary">一栋空楼每天亮起一盏灯，调查者必须选择相信谁。</p></article>
</div>
"""

DETAIL = {
    "https://ttnovels.com/book/1-a": """
    <meta name="description" content="雾中来客简介">
    <script type="application/ld+json">{"@type":"Book","name":"雾中来客","author":{"name":"甲"},"genre":"惊悚悬疑","description":"山城封锁后，主角发现失踪者留下的密钥，必须在倒计时前查清真相。"}</script>
    <dl><div><dt>状态：</dt><dd>连载</dd></div></dl>
    <section class="panel chapter-preview"><ol><li><a href="/chapter/1">第一章 雾起</a></li><li><a href="/chapter/2">第二章 密钥</a></li></ol></section>
    """,
    "https://ttnovels.com/book/2-b": """
    <script type="application/ld+json">{"@type":"Book","name":"夜行档案","author":{"name":"乙"},"genre":"惊悚悬疑","description":"刑警在旧案中发现新的尸检线索，追查会付出无法挽回的代价。"}</script>
    <section class="panel chapter-preview"><ol><li><a href="/chapter/3">第一章 旧案</a></li></ol></section>
    """,
    "https://ttnovels.com/book/3-c": """
    <script type="application/ld+json">{"@type":"Book","name":"空楼回声","author":{"name":"丙"},"genre":"惊悚悬疑","description":"一栋空楼每天亮起一盏灯，调查者必须选择相信谁。"}</script>
    """,
}


class SimilarNovelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="similar_novels_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        (self.root / "项目元数据.json").write_text(json.dumps({"title": "自己的书", "genre": "惊悚悬疑"}), encoding="utf-8")

    def test_parse_cards_and_detail_metadata(self):
        cards = similar_novels.parse_cards(CARD_HTML, "https://ttnovels.com/")
        self.assertEqual([row["title"] for row in cards], ["雾中来客", "夜行档案", "空楼回声"])
        detail = similar_novels.parse_detail(DETAIL["https://ttnovels.com/book/1-a"], "https://ttnovels.com/")
        self.assertEqual(detail["genre"], "惊悚悬疑")
        self.assertEqual(detail["chapters"][0]["title"], "第一章 雾起")

    def test_research_selects_three_and_writes_cache_without_body(self):
        def fake_fetch(url):
            if url.endswith("/category/xuanyi") or "/search?" in url:
                return CARD_HTML, url
            return DETAIL[url], url

        report = similar_novels.research(self.root, allow_network=True, fetcher=fake_fetch)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(report["books"]), 3)
        self.assertTrue((self.root / "研究/同类小说研究.json").is_file())
        self.assertTrue((self.root / "研究/同类小说研究.md").is_file())
        self.assertNotIn("chapter_body", json.dumps(report, ensure_ascii=False))
        cached = similar_novels.research(self.root, allow_network=True, fetcher=lambda _: (_ for _ in ()).throw(AssertionError("不应重读")))
        self.assertEqual(cached["status"], "cached")

    def test_originality_guard_flags_long_exact_phrase(self):
        report = {"books": [{"title": "样书", "summary": "主角发现失踪者留下的密钥，必须在倒计时前查清真相。", "chapters": []}]}
        high = similar_novels.originality_check("主角发现失踪者留下的密钥，必须在倒计时前查清真相。", report)
        self.assertEqual(high["risk"], "high")
        low = similar_novels.originality_check("雨水敲在铁皮屋顶，沈砚把旧地图折成四份。", report)
        self.assertEqual(low["risk"], "low")

    def test_disabled_cli_state_is_non_blocking(self):
        result = similar_novels.main([str(self.root)])
        self.assertEqual(result, 0)
        self.assertEqual(similar_novels.load_config(self.root)["enabled"], False)

    def test_pov_preference_is_documented(self):
        rules = (ROOT / "references" / "写作铁律.md").read_text(encoding="utf-8")
        self.assertIn("第三人称、单主角限知视角", rules)
        self.assertIn("必要时少量切换角色视角", rules)


if __name__ == "__main__":
    unittest.main()
