# -*- coding: utf-8 -*-
"""
mochi_check.py — 网络小说创作技能 v7.7 墨尺本地AI味检测（朱雀额度用尽的本地兜底）
工具: 墨尺 mochi-ruler（github.com/yycqyjq/mochi-ruler，MIT，纯标准库本地服务）
     评分 0-10、**越高越像真人**（注意：与朱雀 ai_pct / AI味指数方向相反）
用法: python mochi_check.py <章节文件.md|txt> [--min 6] [--floor 5] [--top 5]
                                     [--url http://127.0.0.1:8765] [--timeout 60]
     python mochi_check.py --book <项目根> [--only 3,7-12] [--delay 0] [其余同上]
服务: 默认连 http://127.0.0.1:8765。服务没起时：
     设了环境变量 MOCHI_RULER_DIR（墨尺仓库路径）→ 自动启动 server.py；
     没设 → 提示手动启动（cd 墨尺目录 && python server.py）后退出码 2。
判定: 每章总分 total（0-10）换算百分制人类分 = total×10（与朱雀「人类分≥90」同一条交付线）
     human ≥ min×10（默认90）通过；floor×10 ≤ human < min×10（默认80-89）警告；
     human < floor×10（默认<80）→ 退出码 1 禁止交付，按最差指标项定向改写。
退出码: 0=通过, 1=存在不达标章(禁止交付), 2=输入/配置错误(文件不存在/服务起不来),
        3=分析失败章(服务500等；全书=存在失败章且无不达标章)
报告: --book 模式落盘 <项目根>/mind/墨尺检测报告.md（轮次/较上轮/待修复清单/最差指标）
阈值真源: references/常量表.md「六、AI味检测（朱雀线上 + 墨尺本地）」
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_chapter import count_chars, load_text  # noqa: E402
from gen_index import collect_chapters  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8765"
KEY_ENV_DIR = "MOCHI_RULER_DIR"
REPORT_NAME = os.path.join("mind", "墨尺检测报告.md")
MIN_CHARS = 50  # 与朱雀通路一致的送检下限

DIMS = [("real", "真人感"), ("human", "人味"), ("imm", "代入感"), ("rhy", "节奏"), ("syn", "句法")]


def parse_only(spec):
    out = set()
    for part in (spec or "").split(","):
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


def ensure_server(base_url, timeout=10.0):
    """探测墨尺服务；没起且 MOCHI_RULER_DIR 可用则自动启动。成功返回 None，失败返回原因 str。"""
    host = base_url.split("//")[-1]
    port = host.split(":")[1] if ":" in host else "8765"

    def alive():
        try:
            urllib.request.urlopen(base_url + "/", timeout=2)
            return True
        except urllib.error.HTTPError:
            return True  # 服务在，只是路径不回 200
        except (urllib.error.URLError, OSError):
            return False

    if alive():
        return None
    ruler_dir = os.environ.get(KEY_ENV_DIR, "")
    server_py = os.path.join(ruler_dir, "server.py") if ruler_dir else ""
    if not server_py or not os.path.isfile(server_py):
        return (f"墨尺服务未启动（{base_url}）。二选一：\n"
                f"    a) 手动启动：cd <墨尺目录> && python server.py\n"
                f"    b) 设环境变量 {KEY_ENV_DIR}=<墨尺仓库路径>，本脚本自动启动")
    subprocess.Popen([sys.executable, "server.py", port], cwd=ruler_dir,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if alive():
            print(f"[i] 已自动启动墨尺服务（{KEY_ENV_DIR}={ruler_dir}，端口 {port}）")
            return None
        time.sleep(0.5)
    return f"自动启动墨尺服务超时（{timeout:.0f}s），请手动启动后重试"


def call_analyze(base_url, text, name, timeout):
    """POST /api/analyze。成功返回 dict，失败抛 RuntimeError。"""
    payload = json.dumps({"text": text, "name": name}).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/api/analyze", data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:150]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}：{detail or e.reason}")
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"连接墨尺服务失败：{e}")
    except json.JSONDecodeError:
        raise RuntimeError("响应不是合法 JSON")
    if not isinstance(data, dict) or "chapters" not in data:
        raise RuntimeError(f"响应异常：{str(data)[:150]}")
    return data


def worst_items(items, top):
    """40 项逐项分里取最低的前 top 项（<7 才算值得看的短板）。"""
    rows = sorted(((k, v) for k, v in items.items() if v < 7), key=lambda x: x[1])
    return [f"{k}={v:.1f}" for k, v in rows[:top]]


def evaluate(total, floor, min_):
    if total < floor:
        return "fail"
    if total < min_:
        return "warn"
    return "pass"


# ─────────────── 报告（与朱雀报告同构：轮次/合并/较上轮）───────────────

def load_prev_report(path):
    """读上一轮墨尺报告 -> (轮次, {章号: total}, {章号: 行dict})。"""
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
                if len(cells) < 10 or not cells[0].isdigit():
                    continue
                num = int(cells[0])
                if re.fullmatch(r"[\d.]+", cells[2]):
                    prev[num] = float(cells[2])
                    verdict = cells[9]
                    level = ("fail" if "不达标" in verdict else
                             "warn" if "警告" in verdict else
                             "error" if "失败" in verdict else "pass")
                    rows[num] = {"num": num, "title": cells[1], "level": level,
                                 "total": float(cells[2]),
                                 "dims": [float(cells[i]) for i in range(3, 8)],
                                 "prev": None, "weak": [], "reused": True}
                elif "失败" in cells[9]:
                    rows[num] = {"num": num, "title": cells[1], "level": "error",
                                 "prev": None, "weak": [], "reused": True}
    except OSError:
        return 0, {}, {}
    return rnd, prev, rows


def write_report(path, rnd, rows, floor, min_):
    n_fail = sum(1 for r in rows if r["level"] == "fail")
    n_warn = sum(1 for r in rows if r["level"] == "warn")
    n_err = sum(1 for r in rows if r["level"] == "error")
    n_pass = len(rows) - n_fail - n_warn - n_err
    lines = [
        f"# 墨尺检测报告（轮次：{rnd} ｜ {time.strftime('%Y-%m-%d %H:%M')}）",
        "",
        f"参数：达标线{min_*10:g}分/硬下限{floor*10:g}分（人类分=total×10，100满分） ｜ 送检 {len(rows)} 章 ｜ "
        f"通过 {n_pass} ｜ 警告 {n_warn} ｜ **不达标 {n_fail}** ｜ 失败 {n_err}",
        "",
        "| 章号 | 标题 | 总分 | 真人感 | 人味 | 代入感 | 节奏 | 句法 | 较上轮 | 结论 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["level"] == "error":
            lines.append(f"| {r['num']} | {r['title']} | - | - | - | - | - | - | - | 检测失败 |")
            continue
        if r.get("reused"):
            delta_s = "上轮值"
        else:
            delta = r["total"] - r["prev"] if r["prev"] is not None else None
            delta_s = f"{delta:+.1f}" if delta is not None else "-"
        verdict = {"fail": "**不达标**", "warn": "警告", "pass": "通过"}[r["level"]]
        d = r["dims"]
        lines.append(f"| {r['num']} | {r['title']} | {r['total']:.1f} | {d[0]:.1f} | {d[1]:.1f}"
                     f" | {d[2]:.1f} | {d[3]:.1f} | {d[4]:.1f} | {delta_s} | {verdict} |")
    fix_list = [r for r in rows if r["level"] in ("fail", "warn")]
    err_list = [r for r in rows if r["level"] == "error"]
    lines.append("")
    if fix_list:
        lines.append("## 待修复清单（总分低优先；按最差指标项交《去AI味手册》8 Gate 定向改写）")
        lines.append("")
        for r in fix_list:
            weak = "、".join(r["weak"]) if r["weak"] else "（沿用上轮，重测后出短板项）"
            lines.append(f"- **第{r['num']}章 {r['title']}** total={r['total']:.1f}"
                         f"（{r['level']}{'，上轮数据' if r.get('reused') else ''}）短板：{weak}")
    if err_list:
        lines.append("## 检测失败（未测出≠不达标，排查后 --only 重测）")
        lines.append("")
        for r in err_list:
            lines.append(f"- 第{r['num']}章 {r['title']}")
    if not fix_list and not err_list:
        lines.append("## 待修复清单")
        lines.append("")
        lines.append("无——全部章节达标，可交付。")
    lines.append("")
    lines.append("> 循环协议：修复后 `--only` 只重测未达标章；单章连续两轮涨幅<0.5分或重测满3轮 → 移交人工。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def analyze_one(base_url, path, top, timeout):
    """读文件→送检。返回 (row, error_str)。"""
    title = os.path.basename(path)
    try:
        text = load_text(path)
        n = count_chars(text)
        if n < MIN_CHARS:
            return None, f"纯正文仅 {n} 字（<{MIN_CHARS}），不足送检"
        data = call_analyze(base_url, text, title, timeout)
        chs = data.get("chapters") or []
        if not chs:
            return None, "响应无章节数据"
        sc = chs[0].get("score") or {}
        total = float(sc.get("total", 0))
        return {
            "total": total,
            "dims": [float(sc.get(k, 0)) for k, _ in DIMS],
            "weak": worst_items(chs[0].get("items") or {}, top),
            "violations": len(chs[0].get("violations") or []),
        }, None
    except RuntimeError as e:
        return None, str(e)


def run_single(args):
    if not os.path.isfile(args.file):
        print(f"[✗] 文件不存在：{args.file}")
        return 2
    err = ensure_server(args.url)
    if err:
        print(f"[✗] {err}")
        return 2
    print(f"[i] 墨尺本地检测：{os.path.basename(args.file)}（0-10 分，越高越像真人）")
    row, error = analyze_one(args.url, args.file, args.top, args.timeout)
    if error:
        print(f"[✗] 检测未完成：{error}")
        print("    注意：未测出 ≠ 不达标，本结论不触发交付闸门；排查后重跑即可")
        return 2 if "不足送检" in error else 3
    lvl = evaluate(row["total"], args.floor, args.min)
    human = row["total"] * 10
    dims_s = " ｜ ".join(f"{cn} {v:.1f}" for (_, cn), v in zip(DIMS, row["dims"]))
    print(f"[i] 五维：{dims_s}")
    print(f"[i] 人类分 {human:.0f}/100（total×10）")
    if row["weak"]:
        print(f"[i] 短板指标（低分前{args.top}）：{'、'.join(row['weak'])}")
    if row["violations"]:
        print(f"[!] 合规违规 {row['violations']} 处（详见墨尺网页端）")
    print("-" * 46)
    if lvl == "fail":
        print(f"[✗] 人类分 {human:.0f} < 硬下限 {args.floor*10:g} —— 禁止交付")
        print(f"结论：墨尺检测未通过（人类分 {human:.0f} < {args.floor*10:g}）")
        print(f"摘要：墨尺人类分={human:.0f}（total={row['total']:.1f}；真人感{row['dims'][0]:.1f}"
              f"/人味{row['dims'][1]:.1f}/代入{row['dims'][2]:.1f}/节奏{row['dims'][3]:.1f}"
              f"/句法{row['dims'][4]:.1f}） —— 按短板指标定向改写后重测")
        return 1
    if lvl == "warn":
        print(f"[!] 人类分 {human:.0f}（≥硬下限 {args.floor*10:g}，<达标线 {args.min*10:g}）"
              f"—— 通过，但须按短板指标过目")
        print("结论：墨尺检测通过（带警告）✓")
        print(f"摘要：墨尺人类分={human:.0f}（total={row['total']:.1f}） —— 人工过目短板指标后可交付")
        return 0
    print(f"[✓] 人类分 {human:.0f} ≥ 达标线 {args.min*10:g}，读感达标")
    print("结论：墨尺检测通过 ✓")
    print(f"摘要：墨尺人类分={human:.0f}（total={row['total']:.1f}） —— 可交付")
    return 0


def run_book(args):
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
    err = ensure_server(args.url)
    if err:
        print(f"[✗] {err}")
        return 2

    report_path = os.path.join(args.book, REPORT_NAME)
    prev_rnd, prev_map, prev_rows = load_prev_report(report_path)
    rnd = prev_rnd + 1
    tested = {c[0] for c in chapters}
    rows = [prev_rows[num] for num in sorted(prev_rows) if num not in tested]
    print(f"[i] 墨尺全书检测 第{rnd}轮：本轮检测 {len(chapters)} 章"
          f"（通过线{args.min:g}/硬下限{args.floor:g}，总分越高越好"
          f"{'，其余 ' + str(len(rows)) + ' 章沿用上轮' if rows else ''}）")

    for i, (num, fname, title) in enumerate(chapters):
        label = f"第{num}章 {title or ''}".strip()
        row, error = analyze_one(args.url, os.path.join(book_dir, fname), args.top, args.timeout)
        if error:
            rows.append({"num": num, "title": title or fname, "level": "error",
                         "prev": None, "weak": [], "reused": False})
            print(f"[!] {label}：检测失败——{error}")
        else:
            lvl = evaluate(row["total"], args.floor, args.min)
            mark = {"fail": "[✗]", "warn": "[!]", "pass": "[✓]"}[lvl]
            print(f"{mark} {label}：人类分={row['total']*10:.0f}（total={row['total']:.1f}；"
                  f"真人感{row['dims'][0]:.1f}/节奏{row['dims'][3]:.1f}）")
            rows.append({"num": num, "title": title or fname, "level": lvl,
                         "total": row["total"], "dims": row["dims"],
                         "prev": prev_map.get(num), "weak": row["weak"], "reused": False})
        if i < len(chapters) - 1 and args.delay > 0:
            time.sleep(args.delay)

    mind_dir = os.path.dirname(report_path)
    if mind_dir and not os.path.isdir(mind_dir):
        os.makedirs(mind_dir, exist_ok=True)
    rows.sort(key=lambda r: r["num"])
    write_report(report_path, rnd, rows, args.floor, args.min)

    n_fail = sum(1 for r in rows if r["level"] == "fail")
    n_warn = sum(1 for r in rows if r["level"] == "warn")
    n_err = sum(1 for r in rows if r["level"] == "error")
    print("-" * 46)
    print(f"报告已写入：{report_path}")
    if n_fail:
        print(f"结论：第{rnd}轮检测未通过——不达标 {n_fail} 章、警告 {n_warn} 章。"
              f"按报告「待修复清单」短板指标定向改写后 --only 重测。")
        return 1
    if n_err:
        print(f"结论：有 {n_err} 章检测失败（未测出≠不达标），排查后 --only 重测失败章。")
        return 3
    print(f"结论：第{rnd}轮全部通过 ✓（其中警告 {n_warn} 章需按短板指标过目）")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="墨尺本地AI味检测 v7.7（0-10分越高越像真人；朱雀额度用尽的本地兜底）",
        epilog="服务：默认 127.0.0.1:8765，设 MOCHI_RULER_DIR=<墨尺仓库路径> 可自动启动。"
               "退出码 0=通过 / 1=不达标禁止交付 / 2=输入或配置错误 / 3=分析失败。")
    ap.add_argument("file", nargs="?", help="章节文件（.md/.txt）；与 --book 二选一")
    ap.add_argument("--book", default="", metavar="项目根",
                    help="全书模式：扫 <项目根>/书稿/ 逐章检测，报告落盘 mind/墨尺检测报告.md")
    ap.add_argument("--only", default="", help="全书模式重测指定章（示例：3,7-12）")
    ap.add_argument("--min", type=float, default=9, help="总分通过线0-10（默认9=人类分90，真源=常量表·六）")
    ap.add_argument("--floor", type=float, default=8, help="总分硬下限0-10（默认8=人类分80，低于禁止交付）")
    ap.add_argument("--top", type=int, default=5, help="展示最差指标项个数（默认5）")
    ap.add_argument("--url", default=DEFAULT_URL, help="墨尺服务地址（默认 127.0.0.1:8765）")
    ap.add_argument("--delay", type=float, default=0, help="全书模式章节间隔秒数（本地默认0）")
    ap.add_argument("--timeout", type=int, default=60, help="单章分析超时秒数（默认60）")
    args = ap.parse_args()

    if not args.book and not args.file:
        ap.error("需要章节文件路径，或 --book <项目根> 进入全书模式")
    if args.floor > args.min:
        ap.error("--floor 不能大于 --min")
    if args.book:
        sys.exit(run_book(args))
    sys.exit(run_single(args))


if __name__ == "__main__":
    main()
