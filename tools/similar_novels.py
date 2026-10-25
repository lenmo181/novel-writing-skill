# -*- coding: utf-8 -*-
"""同类小说研究与原创性护栏（标准库实现）。

默认适配 TTNovels（天天小说库）。工具只读取公开的分类页、详情页元数据、
简介和章节标题，不抓取、保存或输出章节正文；研究结果只沉淀为结构卡，供
作者重新设计冲突、人物和场景。网络访问必须由项目配置或 ``--allow-network``
明确开启，报告带来源链接和抓取时间，便于复核与删除。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable

from config import SKILL_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


DEFAULT_SOURCE = "https://ttnovels.com/"
CONFIG_REL = Path("研究") / "同类小说配置.json"
REPORT_JSON_REL = Path("研究") / "同类小说研究.json"
REPORT_MD_REL = Path("研究") / "同类小说研究.md"
USER_AGENT = "web-novel-writing-similar-research/1.0 (+local-authoring)"
MAX_PAGE_BYTES = 1_500_000
MIN_REQUEST_INTERVAL = 0.75

GENRE_SLUGS = {
    "玄幻": "xuanhuan", "玄幻魔幻": "xuanhuan", "都市": "dushi",
    "言情": "yanqing", "现代言情": "yanqing", "豪门": "haomen",
    "穿越": "chuanyue", "重生": "chongsheng", "古言": "jiakong",
    "古代言情": "jiakong", "仙侠": "xianxia", "科幻": "kehuan",
    "无限流": "wuxian", "悬疑": "xuanyi", "惊悚": "xuanyi",
    "历史": "lishi", "历史脑洞": "lishi", "军事": "junshi",
    "游戏": "youxi", "体育": "tiyu", "同人": "tongren",
}
GENRE_MARKERS = {
    "悬疑": ("悬疑", "惊悚", "刑侦", "诡异", "灵异", "探案", "谜案"),
    "灵异": ("灵异", "鬼", "尸", "诡", "阴间", "冥"),
    "玄幻": ("玄幻", "修炼", "宗门", "灵气", "天才", "系统"),
    "仙侠": ("仙", "修行", "宗门", "飞升", "剑", "道"),
    "都市": ("都市", "公司", "职场", "系统", "娱乐", "直播"),
    "言情": ("爱", "婚", "妻", "夫", "恋", "重生", "豪门"),
    "穿越": ("穿越", "古代", "王爷", "宫", "侯府"),
    "重生": ("重生", "前世", "复仇", "再来一次"),
    "科幻": ("末世", "星际", "宇宙", "机甲", "基地", "未来"),
    "历史": ("大明", "大唐", "三国", "历史", "皇帝", "官场"),
}
STOPWORDS = set("的了是我你他她它和与在有将被这那一个一场然后因为所以以及小说作者简介故事开始当前最新章节" )


def _clean(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


def _absolute(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(href or "").strip())


def _same_site(url: str, base: str) -> bool:
    return urllib.parse.urlparse(url).netloc.lower() == urllib.parse.urlparse(base).netloc.lower()


class BookCardParser(HTMLParser):
    """解析分类/搜索页的书卡，不读取正文。"""

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.cards: list[dict] = []
        self.card: dict | None = None
        self.capture = ""
        self.buffer: list[str] = []
        self.anchor_href = ""

    @staticmethod
    def _classes(attrs) -> set[str]:
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = self._classes(attrs)
        if tag == "article" and "book-card" in classes:
            self.card = {"title": "", "author": "", "summary": "", "url": ""}
        if not self.card:
            return
        if tag == "a" and "book-cover" in classes:
            self.card["url"] = _absolute(self.base, attrs_dict.get("href", ""))
        if tag == "h3":
            self.capture, self.buffer = "title", []
        elif tag == "p" and "book-author" in classes:
            self.capture, self.buffer = "author", []
        elif tag == "p" and "book-summary" in classes:
            self.capture, self.buffer = "summary", []

    def handle_data(self, data):
        if self.card and self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if not self.card:
            return
        if self.capture and tag in {"h3", "p"}:
            self.card[self.capture] = _clean("".join(self.buffer))
            self.capture, self.buffer = "", []
        if tag == "article":
            if self.card.get("title") and self.card.get("url"):
                self.cards.append(self.card)
            self.card = None


class BookDetailParser(HTMLParser):
    """解析详情页公开元数据、简介和章节标题。"""

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.dl_key = ""
        self.dl_value: list[str] = []
        self.summary_depth = 0
        self.chapter_depth = 0
        self.capture = ""
        self.buffer: list[str] = []
        self.chapters: list[dict] = []
        self.script_depth = 0
        self.script_buffer: list[str] = []

    @staticmethod
    def _classes(attrs) -> set[str]:
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        classes = self._classes(attrs)
        if tag == "meta" and d.get("name") in {"description", "author"}:
            self.meta[d["name"]] = _clean(d.get("content", ""))
        if tag == "meta" and d.get("property") in {"og:description", "og:title"}:
            self.meta[d["property"]] = _clean(d.get("content", ""))
        if tag == "script" and d.get("type") == "application/ld+json":
            self.script_depth, self.script_buffer = 1, []
        elif self.script_depth and tag == "script":
            self.script_depth += 1
        if tag == "dt":
            self.capture, self.buffer = "dt", []
        elif tag == "dd":
            self.capture, self.buffer = "dd", []
        if "summary-copy" in classes:
            self.summary_depth = 1
        elif self.summary_depth:
            self.summary_depth += 1
        if "chapter-preview" in classes:
            self.chapter_depth = 1
        elif self.chapter_depth:
            self.chapter_depth += 1
        if self.chapter_depth and tag == "a":
            self.capture = "chapter"
            self.buffer = []
            self._chapter_href = _absolute(self.base, d.get("href", ""))

    def handle_data(self, data):
        if self.script_depth:
            self.script_buffer.append(data)
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.script_depth and tag == "script":
            self.jsonld.append("".join(self.script_buffer))
            self.script_depth = 0
            self.script_buffer = []
        if self.capture == "dt" and tag == "dt":
            self.dl_key, self.capture, self.buffer = _clean("".join(self.buffer)).rstrip("：:"), "", []
        elif self.capture == "dd" and tag == "dd":
            if self.dl_key:
                self.meta[self.dl_key] = _clean("".join(self.buffer))
            self.capture, self.buffer = "", []
        elif self.capture == "chapter" and tag == "a":
            title = _clean("".join(self.buffer))
            if title and title not in {"查看全部章节", "查看章节目录"} and getattr(self, "_chapter_href", "") and not self._chapter_href.rstrip("/").endswith("/chapters"):
                self.chapters.append({"title": title, "url": self._chapter_href})
            self.capture, self.buffer = "", []
        if self.summary_depth:
            self.summary_depth -= 1
        if self.chapter_depth:
            self.chapter_depth -= 1


def parse_cards(text: str, base: str) -> list[dict]:
    parser = BookCardParser(base)
    parser.feed(text)
    return parser.cards


def parse_detail(text: str, base: str) -> dict:
    parser = BookDetailParser(base)
    parser.feed(text)
    data = dict(parser.meta)
    for raw in parser.jsonld:
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            continue
        items = obj if isinstance(obj, list) else obj.get("@graph", []) if isinstance(obj, dict) else []
        if isinstance(obj, dict) and not items:
            items = [obj]
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("name", "author", "genre", "description", "url"):
                value = item.get(key)
                if isinstance(value, dict):
                    value = value.get("name", "")
                if value and (key not in data or key == "description"):
                    data[key] = _clean(str(value))
    data["chapters"] = parser.chapters
    return data


def _fetch(url: str, *, opener=urllib.request.urlopen) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with opener(request, timeout=20) as response:
        raw = response.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise ValueError(f"页面超过 {MAX_PAGE_BYTES} 字节，已拒绝读取")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace"), response.geturl()


def _robots(base: str, opener=urllib.request.urlopen) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
    url = urllib.parse.urljoin(base, "/robots.txt")
    try:
        text, _ = _fetch(url, opener=opener)
    except urllib.error.HTTPError as exc:
        return None, f"robots.txt HTTP {exc.code}；未能核实规则，已限制为公开页面、3 本、低速访问"
    except (OSError, ValueError) as exc:
        return None, f"robots.txt 不可用（{exc}）；已限制为公开页面、3 本、低速访问"
    parser = urllib.robotparser.RobotFileParser(url)
    parser.parse(text.splitlines())
    return parser, "robots.txt 已读取"


def _genre_slug(genre: str) -> str:
    for key, slug in GENRE_SLUGS.items():
        if key in genre:
            return slug
    return ""


def _markers(genre: str) -> tuple[str, ...]:
    found: list[str] = []
    for key, values in GENRE_MARKERS.items():
        if key in genre:
            found.extend(values)
    return tuple(dict.fromkeys(found)) or tuple(re.findall(r"[\u4e00-\u9fff]{2,4}", genre))


def _score(card: dict, genre: str) -> int:
    text = " ".join(card.get(k, "") for k in ("title", "summary", "author"))
    markers = _markers(genre)
    return sum(2 if marker in card.get("title", "") else 1 for marker in markers if marker in text)


def _select(cards: Iterable[dict], title: str, genre: str, count: int) -> list[dict]:
    seen: set[str] = set()
    candidates = []
    for card in cards:
        name = _clean(card.get("title", ""))
        if not name or name == title or name in seen:
            continue
        seen.add(name)
        card = dict(card)
        card["match_score"] = _score(card, genre)
        candidates.append(card)
    candidates.sort(key=lambda row: (-row["match_score"], row.get("title", "")))
    selected: list[dict] = []
    authors: set[str] = set()
    for card in candidates:
        author = card.get("author", "")
        if len(selected) < count and author and author not in authors:
            selected.append(card)
            authors.add(author)
    for card in candidates:
        if len(selected) >= count:
            break
        if card not in selected:
            selected.append(card)
    return selected[:count]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?；;]+", _clean(text)) if s.strip()]


def _summary_body(text: str) -> str:
    """去掉站点卡片的书名/作者前缀，避免结构卡只重复 SEO 元描述。"""
    value = _clean(text)
    value = re.sub(r"^《[^》]+》\s*[,，]\s*作者\s*[:：]\s*[^,，。]+\s*[,，]\s*简介\s*[:：]", "", value)
    value = re.sub(r"^简介\s*[:：]", "", value)
    return value.strip(" ：:，,")


def _first_matching(sentences: list[str], words: Iterable[str]) -> str:
    for sentence in sentences:
        if any(word in sentence for word in words):
            return sentence
    return sentences[0] if sentences else "简介未提供，需人工核实"


def derive_structure(book: dict, genre: str) -> dict:
    summary = _summary_body(book.get("description", "") or book.get("summary", ""))
    sentences = _sentences(summary)
    titles = [item.get("title", "") for item in book.get("chapters", []) if item.get("title")]
    premise = sentences[0] if sentences else "简介未提供，需人工核实"
    return {
        "前提": premise,
        "引爆点": _first_matching(sentences, ("突然", "发现", "重生", "穿越", "系统", "被", "一旦", "某天", "醒来")),
        "主线驱动": _first_matching(sentences, ("必须", "为了", "寻找", "保护", "逃", "复仇", "调查", "完成", "活下去")),
        "压力与代价": _first_matching(sentences, ("否则", "代价", "追杀", "死亡", "危机", "不能", "倒计时", "失去")),
        "目录节奏信号": {
            "开篇标题": titles[:3],
            "近期标题": titles[-3:] if len(titles) > 3 else titles,
            "观察": "仅根据公开简介和章节标题推断；不得当作原作事实扩写。",
        },
        "可迁移结构": [
            f"借鉴“{genre or '同题材'}”常见的目标—阻碍—转折链，重新设计人物动机。",
            "把简介中的引爆点改写成自己的场景、道具和代价，不沿用原作专名。",
            "只参考目录的节奏功能（开局立钩、升级压力、阶段转折），不照搬章节顺序。",
        ],
    }


def _cjk_ngrams(text: str, size: int = 6) -> set[str]:
    chunks = re.findall(r"[\u4e00-\u9fff]{%d,}" % size, _clean(text))
    return {chunk[i:i + size] for chunk in chunks for i in range(len(chunk) - size + 1)}


def originality_check(draft: str, report: dict) -> dict:
    """检查草稿与研究材料的连续片段重合；只作风险提示，不替作者判定抄袭。"""
    draft = _clean(draft)
    if not draft:
        return {"status": "no_draft", "risk": "unknown", "exact_hits": [], "overlap": 0.0}
    sources: list[str] = []
    for book in report.get("books", []):
        sources.extend([book.get("title", ""), book.get("summary", ""), book.get("description", "")])
        sources.extend(item.get("title", "") for item in book.get("chapters", []))
    draft_ngrams = _cjk_ngrams(draft)
    source_ngrams = set().union(*(_cjk_ngrams(value) for value in sources if value)) if sources else set()
    common = sorted(draft_ngrams & source_ngrams, key=len, reverse=True)
    exact_hits = []
    normalized = re.sub(r"\s+", "", draft)
    for source in sources:
        for sentence in _sentences(source):
            phrase = re.sub(r"\s+", "", sentence)
            if len(phrase) >= 12 and phrase in normalized:
                exact_hits.append(phrase[:80])
    exact_hits = list(dict.fromkeys(exact_hits))[:10]
    overlap = len(common) / max(1, len(draft_ngrams))
    if exact_hits:
        risk = "high"
    elif overlap >= 0.08 or len(common) >= 8:
        risk = "medium"
    else:
        risk = "low"
    return {
        "status": "checked", "risk": risk, "exact_hits": exact_hits,
        "overlap": round(overlap, 4), "common_fragments": common[:12],
        "action": "出现连续原句或高重合：更换人物目标、场景因果、专名和转折顺序，再复核。" if risk != "low" else "未发现明显连续片段；仍需人工确认冲突与人物设定独立。",
    }


def load_config(root: Path) -> dict:
    path = root / CONFIG_REL
    defaults = {"enabled": False, "allow_network": False, "source": DEFAULT_SOURCE, "count": 3,
                "refresh_hours": 24, "request_interval": MIN_REQUEST_INTERVAL}
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    defaults.update({k: v for k, v in data.items() if k in defaults})
    return defaults


def _fresh_report(path: Path, genre: str, source: str, hours: float) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        timestamp = datetime.fromisoformat(data.get("retrieved_at", "").replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
    except (OSError, ValueError, TypeError):
        return None
    if age <= max(0.0, float(hours)) and data.get("genre") == genre and data.get("source") == source:
        return data
    return None


def research(root: Path, *, genre: str = "", title: str = "", source: str = DEFAULT_SOURCE,
             count: int = 3, allow_network: bool = False, refresh: bool = False,
             fetcher: Callable[[str], tuple[str, str]] | None = None,
             opener=urllib.request.urlopen) -> dict:
    root = Path(root).expanduser().resolve()
    config = load_config(root)
    metadata_path = root / "项目元数据.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
            genre = genre or str(metadata.get("genre", ""))
            title = title or str(metadata.get("title", ""))
        except (OSError, ValueError):
            pass
    source = source.rstrip("/") + "/"
    count = max(1, min(3, int(count)))
    report_path = root / REPORT_JSON_REL
    if not refresh:
        cached = _fresh_report(report_path, genre, source, float(config.get("refresh_hours", 24)))
        if cached:
            cached["status"] = "cached"
            return cached
    if not allow_network:
        return {"version": SKILL_VERSION, "status": "network_not_authorized", "genre": genre,
                "source": source, "books": [], "message": "联网研究未授权；设置配置 allow_network=true 或传 --allow-network。"}
    parsed_source = urllib.parse.urlparse(source)
    if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
        return {"version": SKILL_VERSION, "status": "invalid_source", "source": source, "books": []}
    if fetcher is not None:
        robots, robots_note = None, "测试/注入读取器：未访问 robots.txt"
    else:
        robots, robots_note = _robots(source, opener=opener)
    last_request = [0.0]
    def get(url: str) -> tuple[str, str]:
        if not _same_site(url, source):
            raise ValueError("拒绝跨站读取：" + url)
        if robots and not robots.can_fetch(USER_AGENT, url):
            raise PermissionError("robots.txt 不允许读取：" + url)
        wait = float(config.get("request_interval", MIN_REQUEST_INTERVAL)) - (time.monotonic() - last_request[0])
        if wait > 0:
            time.sleep(wait)
        last_request[0] = time.monotonic()
        return (fetcher or (lambda u: _fetch(u, opener=opener)))(url)
    slug = _genre_slug(genre)
    candidates: list[dict] = []
    pages: list[str] = []
    if slug:
        pages.append(urllib.parse.urljoin(source, "category/" + slug))
    if genre:
        pages.append(urllib.parse.urljoin(source, "search?q=" + urllib.parse.quote(genre)))
    errors: list[str] = []
    for page in pages:
        try:
            text, _ = get(page)
            candidates.extend(parse_cards(text, source))
            if len(candidates) >= count * 4:
                break
        except (OSError, ValueError, PermissionError, urllib.error.URLError) as exc:
            errors.append(f"{page}: {exc}")
    selected = _select(candidates, title, genre, count)
    books: list[dict] = []
    for card in selected:
        row = dict(card)
        try:
            detail_text, final_url = get(card["url"])
            detail = parse_detail(detail_text, source)
            row.update({key: value for key, value in detail.items() if value})
            row["url"] = final_url
        except (OSError, ValueError, PermissionError, urllib.error.URLError) as exc:
            row["detail_error"] = str(exc)
        row["summary"] = _summary_body(row.get("description", "") or row.get("summary", ""))[:280]
        row["description"] = row.get("summary", "")
        row["chapters"] = row.get("chapters", [])[:9]
        row["structure"] = derive_structure(row, genre)
        # 详情页可能返回过多字段；报告仅保留可复核的公开元数据。
        keep = {key: row.get(key, "") for key in ("title", "author", "url", "summary", "genre", "status", "字数", "更新")}
        keep["chapters"] = row["chapters"]
        keep["structure"] = row["structure"]
        books.append(keep)
    report = {
        "version": SKILL_VERSION, "status": "ok" if books else "no_results", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": source, "genre": genre, "title": title, "robots": robots_note,
        "books": books, "errors": errors,
        "originality_rules": ["不复用书名、角色名、专有名词", "不复用连续12字以上原句", "不按单本作品的章节顺序改写", "至少替换人物目标、场景机制和代价中的两项"],
        "notice": "仅依据公开简介与章节标题提炼结构；版权正文不抓取、不保存、不作为可复制素材。",
    }
    root.joinpath("研究").mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / REPORT_MD_REL).write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict) -> str:
    lines = ["# 同类小说研究", "", f"- 状态：{report.get('status', '')}", f"- 题材：{report.get('genre', '')}", f"- 来源：{report.get('source', '')}", f"- 抓取时间：{report.get('retrieved_at', '未抓取')}", "", "> 本报告只保留公开元数据、简介短摘和章节标题；结构卡用于原创设计，不替代原作阅读，不保存章节正文。", ""]
    if report.get("message"):
        lines += [f"{report['message']}", ""]
    for index, book in enumerate(report.get("books", []), 1):
        lines += [f"## {index}. {book.get('title', '未命名')}", "", f"- 作者：{book.get('author', '未提供')}", f"- 分类：{book.get('genre', '未提供')}", f"- 来源：{book.get('url', '')}", f"- 简介短摘：{book.get('summary', '未提供')}", "", "### 结构卡", ""]
        for key, value in book.get("structure", {}).items():
            if isinstance(value, dict):
                lines.append(f"- **{key}**：")
                for subkey, subvalue in value.items():
                    lines.append(f"  - {subkey}：{subvalue}")
            elif isinstance(value, list):
                lines.append(f"- **{key}**：" + "；".join(str(item) for item in value))
            else:
                lines.append(f"- **{key}**：{value}")
        lines.append("")
    if report.get("errors"):
        lines += ["## 访问提示", "", *[f"- {item}" for item in report["errors"]], ""]
    lines += ["## 原创约束", "", *[f"- {item}" for item in report.get("originality_rules", [])], "", report.get("notice", ""), ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"同类小说研究与原创性护栏 v{SKILL_VERSION}")
    parser.add_argument("project", help="小说项目根目录")
    parser.add_argument("--genre", default="", help="题材；省略时读取项目元数据")
    parser.add_argument("--title", default="", help="本书书名；用于排除自身")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="同类小说网站，默认 TTNovels")
    parser.add_argument("--count", type=int, default=3, help="最多选择几本，强制限制为 1-3")
    parser.add_argument("--allow-network", action="store_true", help="明确允许读取公开网页")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存并重新读取")
    parser.add_argument("--check-draft", default="", help="用已有研究 JSON 检查草稿文件的连续片段重合")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if args.check_draft:
        try:
            report = json.loads((root / REPORT_JSON_REL).read_text(encoding="utf-8-sig"))
            draft = Path(args.check_draft).expanduser().read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, ValueError) as exc:
            print(f"[✗] 草稿检查失败：{exc}")
            return 2
        result = originality_check(draft, report)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"原创性风险：{result['risk']}；重合率：{result['overlap']:.2%}\n{result['action']}")
        return 1 if result.get("risk") == "high" else 0
    config = load_config(root)
    if not args.allow_network and not bool(config.get("enabled")):
        report = {"version": SKILL_VERSION, "status": "disabled", "source": config.get("source", DEFAULT_SOURCE),
                  "genre": args.genre, "books": [], "message": "同类小说研究未开启；将联网时先在研究/同类小说配置.json 设置 enabled=true。"}
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report), end="")
        return 0
    allow_network = args.allow_network or (bool(config.get("enabled")) and bool(config.get("allow_network")))
    source = args.source if args.source != DEFAULT_SOURCE else str(config.get("source") or DEFAULT_SOURCE)
    report = research(root, genre=args.genre, title=args.title, source=source, count=args.count,
                      allow_network=allow_network, refresh=args.refresh)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report), end="")
    return 0 if report.get("status") in {"ok", "cached", "network_not_authorized"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
