# -*- coding: utf-8 -*-
"""
zhuque_check.py — 网络小说创作技能 v7.5 朱雀AI文本线上检测
API: 腾讯云 EdgeOne Makers 内置模型 @makers/zhuque-text（仅文本，图片暂不支持）
     POST https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify
单章: python zhuque_check.py <章节文件.md|txt> [--threshold 50] [--warn 30]
                                    [--segments 5] [--no-merge] [--timeout 30]
                                    [--key XXX] [--json]
全书: python zhuque_check.py --book <项目根> [--only 3,7-12] [--delay 1] [其余单章参数]
     扫 <项目根>/书稿/ 逐章检测（章号识别口径与 gen_index.py 一致），
     报告落盘 <项目根>/mind/朱雀检测报告.md（含轮次/上轮对比/待修复清单/重点分段）。
     --only 用于修复后只重测指定章（省额度）。
Key 来源: --key 参数 > 环境变量 ZHUQUE_API_KEY。
     Key 在 EdgeOne 控制台 → Makers → Models → API Key 页面创建；每月免费额度 50 万 token。
判定: ai_pct = labels_ratio["1"] + labels_ratio["2"]（AI + 疑似AI 占比，百分数）
     ai_pct ≥ threshold（默认50）→ 退出码 1 禁止交付
     ai_pct ≥ warn（默认30）    → 警告但通过（须按《去AI味手册》过目）
     否则通过
退出码: 0=通过, 1=AI占比超标(禁止交付; 全书=存在超标章), 2=输入/配置错误(文件不存在/无Key),
        3=API或网络错误（单章=未检出≠超标不触发闸门; 全书=存在失败章且无超标章）
正文口径: 与 check_chapter.py 一致（剥章节标题行与格式行后送检）
阈值真源: references/常量表.md「六、AI味检测（朱雀线上 + 墨尺本地）」
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.dont_write_bytecode = True  # 复用技能内模块时不生成 __pycache__ 残留
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_URL = "https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify"
KEY_ENV = "ZHUQUE_API_KEY"
REPORT_NAME = os.path.join("mind", "朱雀检测报告.md")

# 复用机械校验的正文提取（"校验的字"="送检的字"）与 gen_index 的章节识别口径
from check_chapter import count_chars, load_text, body_lines  # noqa: E402
from gen_index import collect_chapters  # noqa: E402

LABEL_NAMES = {0: "人工", 1: "AI", 2: "疑似AI"}


def evaluate(labels_ratio, threshold, warn):
    """从 labels_ratio 算 AI+疑似占比并定级。返回 (ai_pct, level)，level∈pass/warn/fail。"""
    ai = float(labels_ratio.get("1", 0) or 0)
    suspect = float(labels_ratio.get("2", 0) or 0)
    ai_pct = (ai + suspect) * 100
    if ai_pct >= threshold:
        return ai_pct, "fail"
    if ai_pct >= warn:
        return ai_pct, "warn"
    return ai_pct, "pass"


def call_api(text, key, is_merge, timeout):
    """调用朱雀接口。成功返回 dict；失败抛 RuntimeError（含人类可读原因）。"""
    payload = json.dumps({"text": text, "is_merge": is_merge}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        if e.code in (401, 403):
            raise RuntimeError(f"HTTP {e.code}：Key 无效或无权限（检查 ZHUQUE_API_KEY / 额度）。{detail}")
        raise RuntimeError(f"HTTP {e.code}：{detail or e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误：{e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("响应不是合法 JSON（检查网络代理或网关地址）")
    if not isinstance(data, dict) or data.get("status") != "success":
        msg = data.get("msg", "") if isinstance(data, dict) else str(data)[:200]
        raise RuntimeError(f"接口返回异常：{msg or 'status != success'}")
    return data


def worst_segments(segments, limit, width=40):
    """取 label∈{1,2} 的分段按置信度降序前 limit 个，输出定位行。"""
    rows = [s for s in segments if s.get("label") in (1, 2)]
    rows.sort(key=lambda s: s.get("conf", 0), reverse=True)
    out = []
    for s in rows[:limit]:
        t = str(s.get("text", "")).replace("\n", " ")
        if len(t) > width:
            t = t[:width] + "…"
        pos = s.get("position")
        pos_s = f"[{pos[0]}-{pos[1]}]" if isinstance(pos, (list, tuple)) and len(pos) == 2 else ""
        out.append(f"    seg#{s.get('order', '?')} {pos_s} {LABEL_NAMES[s['label']]}"
                   f" conf={s.get('conf', 0):.3f} 「{t}」")
    return out


# ─────────────── 全书批量模式（--book）───────────────

def parse_only(spec):
    """'3,7-12' -> {3,7,8,9,10,11,12}；解析失败返回 None。"""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d+-\d+", part):
            a, b = (int(x) for x in part.split("-"))
            if a > b:
                return None
            out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
        else:
            return None
    return out or None


def load_prev_report(path):
    """读上一轮报告 -> (轮次, {章号: ai_pct}, {章号: 完整行})。文件不存在或解析失败返回 (0, {}, {})。"""
    if not os.path.isfile(path):
        return 0, {}, {}
    rnd, prev, rows = 0, {}, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.search(r"轮次[:：]\s*(\d+)", line)
                if m:
                    rnd = int(m.group(1))
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 8 or not cells[0].isdigit():
                    continue
                num = int(cells[0])
                if re.fullmatch(r"[\d.]+", cells[5]):
                    prev[num] = float(cells[5])
                    verdict = cells[7]
                    level = ("fail" if "超标" in verdict else
                             "warn" if "警告" in verdict else
                             "error" if "失败" in verdict else "pass")
                    rows[num] = {"num": num, "title": cells[1], "level": level,
                                 "ai": float(cells[2]), "suspect": float(cells[3]),
                                 "human": float(cells[4]), "pct": float(cells[5]),
                                 "prev": None, "segments": [], "reused": True}
                elif "失败" in cells[7]:
                    rows[num] = {"num": num, "title": cells[1], "level": "error",
                                 "prev": None, "segments": [], "reused": True}
    except OSError:
        return 0, {}, {}
    return rnd, prev, rows


def write_report(path, rnd, rows, threshold, warn):
    """rows: [{num,title,ai,suspect,human,pct,level,segments(err=None)}]"""
    n_fail = sum(1 for r in rows if r["level"] == "fail")
    n_warn = sum(1 for r in rows if r["level"] == "warn")
    n_err = sum(1 for r in rows if r["level"] == "error")
    n_pass = len(rows) - n_fail - n_warn - n_err
    lines = [
        f"# 朱雀检测报告（轮次：{rnd} ｜ {time.strftime('%Y-%m-%d %H:%M')}）",
        "",
        f"参数：阈值{threshold:g}%/警告线{warn:g}% ｜ 送检 {len(rows)} 章 ｜ "
        f"通过 {n_pass} ｜ 警告 {n_warn} ｜ **超标 {n_fail}** ｜ 失败 {n_err}",
        "",
        "| 章号 | 标题 | AI% | 疑似% | 人工% | ai_pct | 较上轮 | 结论 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["level"] == "error":
            lines.append(f"| {r['num']} | {r['title']} | - | - | - | - | - | 检测失败 |")
            continue
        if r.get("reused"):
            delta_s = "上轮值"
        else:
            delta = r["pct"] - r["prev"] if r["prev"] is not None else None
            delta_s = f"{delta:+.1f}" if delta is not None else "-"
        verdict = {"fail": "**超标**", "warn": "警告", "pass": "通过"}[r["level"]]
        lines.append(f"| {r['num']} | {r['title']} | {r['ai']:.1f} | {r['suspect']:.1f} |"
                     f" {r['human']:.1f} | {r['pct']:.1f} | {delta_s} | {verdict} |")
    fix_list = [r for r in rows if r["level"] in ("fail", "warn")]
    err_list = [r for r in rows if r["level"] == "error"]
    lines.append("")
    if fix_list:
        lines.append("## 待修复清单（超标优先，按《去AI味手册》8 Gate 定向改写）")
        lines.append("")
        for r in fix_list:
            head = (f"- **第{r['num']}章 {r['title']}** ai_pct={r['pct']:.1f}%（{r['level']}"
                    f"{'，上轮数据' if r.get('reused') else ''}）")
            lines.append(head)
            for seg in r["segments"]:
                lines.append("  " + seg.strip())
    if err_list:
        lines.append("## 检测失败（未检出≠超标，排查后 --only 重测）")
        lines.append("")
        for r in err_list:
            lines.append(f"- 第{r['num']}章 {r['title']}")
    if not fix_list and not err_list:
        lines.append("## 待修复清单")
        lines.append("")
        lines.append("无——全部章节达标，可交付。")
    lines.append("")
    lines.append("> 循环协议：修复后 `--only` 只重测未达标章；单章连续两轮降幅<5个百分点或重测满3轮 → 移交人工。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_book(args, key):
    book_dir = os.path.join(args.book, "书稿")
    if not os.path.isdir(book_dir):
        print(f"[✗] 书稿目录不存在：{book_dir}")
        return 2
    chapters = collect_chapters(book_dir)
    if not chapters:
        print(f"[✗] {book_dir} 下没有可识别的章节文件（第X章_标题.md/.txt）")
        return 2
    only = parse_only(args.only) if args.only else None
    if args.only and only is None:
        print(f"[✗] --only 格式不对：{args.only}（示例：3,7-12）")
        return 2
    if only:
        chapters = [c for c in chapters if c[0] in only]
        if not chapters:
            print(f"[✗] --only {args.only} 在书稿里没有匹配到章节")
            return 2

    report_path = os.path.join(args.book, REPORT_NAME)
    prev_rnd, prev_map, prev_rows = load_prev_report(report_path)
    rnd = prev_rnd + 1
    tested = {c[0] for c in chapters}
    # 重测轮：未重测的章沿用上一轮数据，保证报告始终是全书最新视图
    rows = [prev_rows[num] for num in sorted(prev_rows) if num not in tested]
    n_err = 0
    print(f"[i] 朱雀全书检测 第{rnd}轮：本轮检测 {len(chapters)} 章"
          f"（阈值{args.threshold:g}%/警告线{args.warn:g}%"
          f"{'，其余 ' + str(len(rows)) + ' 章沿用上轮' if rows else ''}）")
    for i, (num, fname, title) in enumerate(chapters):
        label = f"第{num}章 {title or ''}".strip()
        try:
            text = load_text(os.path.join(book_dir, fname))
            lines_, _ = body_lines(text)
            body = "\n".join(lines_)
            n = count_chars(body)
            if n < 50:
                rows.append({"num": num, "title": title or fname, "level": "error",
                             "err": "正文<50字", "prev": None, "segments": []})
                print(f"[!] {label}：正文仅{n}字，跳过（不足送检）")
                continue
            data = call_api(body, key, is_merge=not args.no_merge, timeout=args.timeout)
            ratio = data.get("labels_ratio") or {}
            pct, level = evaluate(ratio, args.threshold, args.warn)
            mark = {"fail": "[✗]", "warn": "[!]", "pass": "[✓]"}[level]
            print(f"{mark} {label}：ai_pct={pct:.1f}%（AI {ratio.get('1', 0) * 100:.1f}"
                  f"/疑似 {ratio.get('2', 0) * 100:.1f}/人工 {ratio.get('0', 0) * 100:.1f}）")
            seg_limit = 3 if level in ("fail", "warn") else 0
            rows.append({
                "num": num, "title": title or fname, "level": level,
                "ai": float(ratio.get("1", 0) or 0) * 100,
                "suspect": float(ratio.get("2", 0) or 0) * 100,
                "human": float(ratio.get("0", 0) or 0) * 100,
                "pct": pct, "prev": prev_map.get(num),
                "segments": worst_segments(data.get("segment_labels") or [], seg_limit, width=60),
            })
        except RuntimeError as e:
            n_err += 1
            rows.append({"num": num, "title": title or fname, "level": "error",
                         "err": str(e)[:60], "prev": None, "segments": []})
            print(f"[!] {label}：检测失败——{e}")
        if i < len(chapters) - 1 and args.delay > 0:
            time.sleep(args.delay)

    mind_dir = os.path.dirname(report_path)
    if mind_dir and not os.path.isdir(mind_dir):
        os.makedirs(mind_dir, exist_ok=True)
    rows.sort(key=lambda r: r["num"])
    write_report(report_path, rnd, rows, args.threshold, args.warn)

    # 退出码按合并后的全书状态判（含沿用上轮的失败/超标章）
    n_fail = sum(1 for r in rows if r["level"] == "fail")
    n_warn = sum(1 for r in rows if r["level"] == "warn")
    n_err = sum(1 for r in rows if r["level"] == "error")
    print("-" * 46)
    print(f"报告已写入：{report_path}")
    if n_fail:
        print(f"结论：第{rnd}轮检测未通过——超标 {n_fail} 章、警告 {n_warn} 章。"
              f"按报告「待修复清单」定向改写后 --only 重测。")
        return 1
    if n_err:
        print(f"结论：有 {n_err} 章检测失败（未检出≠超标），排查后 --only 重测失败章。")
        return 3
    print(f"结论：第{rnd}轮全部通过 ✓（其中警告 {n_warn} 章需按清单过目）")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="朱雀AI文本线上检测 v7.5（EdgeOne Makers @makers/zhuque-text）",
        epilog="Key: --key 或环境变量 ZHUQUE_API_KEY（EdgeOne 控制台 Makers → Models → API Key 创建）。"
               "退出码 0=通过 / 1=超标禁止交付 / 2=输入或配置错误 / 3=API或网络错误。")
    ap.add_argument("file", nargs="?", help="章节文件（.md/.txt）；与 --book 二选一")
    ap.add_argument("--book", default="", metavar="项目根",
                    help="全书模式：扫 <项目根>/书稿/ 逐章检测，报告落盘 mind/朱雀检测报告.md")
    ap.add_argument("--only", default="", help="全书模式重测指定章（示例：3,7-12），省额度")
    ap.add_argument("--delay", type=float, default=1.0, help="全书模式章节间隔秒数（默认1）")
    ap.add_argument("--threshold", type=float, default=50,
                    help="AI+疑似占比硬上限%%（默认50，真源=常量表·六）")
    ap.add_argument("--warn", type=float, default=30,
                    help="AI+疑似占比警告线%%（默认30）")
    ap.add_argument("--segments", type=int, default=5,
                    help="超标/警告时展示 AI 味最重的前 N 个分段（默认5，0=不展示）")
    ap.add_argument("--no-merge", action="store_true",
                    help="段落独立检测（is_merge=false，逐段出置信度；默认合并整体判）")
    ap.add_argument("--timeout", type=int, default=30, help="请求超时秒数（默认30）")
    ap.add_argument("--key", default="", help="API Key（不传则读环境变量 ZHUQUE_API_KEY）")
    ap.add_argument("--json", action="store_true", help="打印接口原始 JSON 响应")
    args = ap.parse_args()

    if not args.book and not args.file:
        ap.error("需要章节文件路径，或 --book <项目根> 进入全书模式")

    key = args.key or os.environ.get(KEY_ENV, "")
    if not key:
        print(f"[✗] 未配置 API Key：传 --key 或设置环境变量 {KEY_ENV}")
        print("    Key 获取：EdgeOne 控制台 → Makers → Models → API Key 页面创建（每月免费 50 万 token）")
        return 2

    if args.book:
        return run_book(args, key)

    if not os.path.isfile(args.file):
        print(f"[✗] 文件不存在或不可读：{args.file}")
        return 2

    text = load_text(args.file)
    lines, _dropped = body_lines(text)   # 与 check_chapter.py 同口径剥标题行/格式行
    body = "\n".join(lines)
    n = count_chars(body)
    if n < 50:
        print(f"[✗] 纯正文仅 {n} 字（<50），不足以送检——检查文件是否为正文内容")
        return 2

    print(f"[i] 朱雀文本检测：{os.path.basename(args.file)}（送检 {n} 字，is_merge={not args.no_merge}）")
    try:
        data = call_api(body, key, is_merge=not args.no_merge, timeout=args.timeout)
    except RuntimeError as e:
        print(f"[✗] 检测未完成：{e}")
        print("    注意：未检出 ≠ 超标，本结论不触发交付闸门；排查后重跑即可")
        return 3

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    ratio = data.get("labels_ratio") or {}
    ai_pct, level = evaluate(ratio, args.threshold, args.warn)
    ai_r = float(ratio.get("1", 0) or 0) * 100
    su_r = float(ratio.get("2", 0) or 0) * 100
    hu_r = float(ratio.get("0", 0) or 0) * 100
    softmax = data.get("softmax_confidence", "?")
    ratio_c = data.get("ratio_confidence", "?")
    usage = (data.get("makers_models_usage") or data.get("usage") or {}).get("total_tokens", "?")

    print(f"[i] 占比：人工 {hu_r:.1f}% ｜ AI {ai_r:.1f}% ｜ 疑似AI {su_r:.1f}%")
    print(f"[i] softmax_confidence={softmax}  ratio_confidence={ratio_c}  计费用量={usage} tokens")

    if level == "fail":
        print(f"[✗] AI+疑似占比 {ai_pct:.1f}% ≥ 阈值 {args.threshold:g}% —— 禁止交付")
        if args.segments > 0:
            segs = worst_segments(data.get("segment_labels") or [], args.segments)
            if segs:
                print("    AI 味最重分段（按置信度，交《去AI味手册》8 Gate 定向改写）：")
                for row in segs:
                    print(row)
        print("-" * 46)
        print(f"结论：朱雀检测未通过（{ai_pct:.1f}% ≥ {args.threshold:g}%）")
        print(f"摘要：朱雀AI+疑似={ai_pct:.1f}%（AI {ai_r:.1f}/疑似 {su_r:.1f}）人工={hu_r:.1f}%"
              f" —— 按《去AI味手册》定向改写后重测")
        return 1

    if level == "warn":
        print(f"[!] AI+疑似占比 {ai_pct:.1f}%（≥警告线 {args.warn:g}%，<阈值 {args.threshold:g}%）"
              f"—— 通过，但须按《去AI味手册》逐段过目")
        if args.segments > 0:
            segs = worst_segments(data.get("segment_labels") or [], args.segments)
            if segs:
                print("    疑似重点分段（交《去AI味手册》8 Gate 定向改写）：")
                for row in segs:
                    print(row)
        print("-" * 46)
        print(f"结论：朱雀检测通过（带警告）✓")
        print(f"摘要：朱雀AI+疑似={ai_pct:.1f}%（AI {ai_r:.1f}/疑似 {su_r:.1f}）人工={hu_r:.1f}%"
              f" 阈值={args.threshold:g}% —— 人工过目警告分段后可交付")
        return 0

    print(f"[✓] AI+疑似占比 {ai_pct:.1f}% < 警告线 {args.warn:g}%，机器判定干净")
    print("-" * 46)
    print("结论：朱雀检测通过 ✓")
    print(f"摘要：朱雀AI+疑似={ai_pct:.1f}%（AI {ai_r:.1f}/疑似 {su_r:.1f}）人工={hu_r:.1f}%"
          f" 阈值={args.threshold:g}% —— 可交付")
    return 0


if __name__ == "__main__":
    sys.exit(main())
