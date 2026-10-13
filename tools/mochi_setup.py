# -*- coding: utf-8 -*-
"""
mochi_setup.py — 网络小说创作技能 v7.45 墨尺一键安装向导（打通AI味默认量化链路）
作用: 定位/安装墨尺 mochi-ruler（github.com/yycqyjq/mochi-ruler，MIT，纯标准库），
     并把仓库路径持久化到 ~/.mochi_ruler_path.json——此后 `mochi_check.py` 无需
     再设会话级环境变量 MOCHI_RULER_DIR，服务未起时自动拉起。
用法: python mochi_setup.py                 # 定位→缺则 clone→持久化→起服自检（默认全做）
     python mochi_setup.py --dir <已有墨尺仓库路径>   # 显式指定，跳过 clone
     python mochi_setup.py --dest <安装目标目录>      # 默认 ~/.mochi-ruler
     python mochi_setup.py --repo <git地址>           # 默认官方仓库（镜像/内网可用）
     python mochi_setup.py --no-verify                # 只装不验（不起服自检）
查找顺序: --dir > 环境变量 MOCHI_RULER_DIR > 持久化文件 ~/.mochi_ruler_path.json > ~/.mochi-ruler
     （与 mochi_check.py 的运行时读取顺序一致；找到即重写持久化文件，换目录重跑本向导即可）
退出码: 0=墨尺就绪（或已就绪且自检通过）, 1=安装/自检失败, 2=参数或路径配置错误
验证: 起服后 POST /api/analyze 送检样章文本，回包含 chapters[0].score.total 才算通过
     （与 mochi_check.py 的回包解析契约一致）；自检失败给出手动兜底指引
     （git clone + 设 MOCHI_RULER_DIR），不影响已有交付闸门。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RULER_REPO = "https://github.com/yycqyjq/mochi-ruler.git"
KEY_ENV_DIR = "MOCHI_RULER_DIR"
PATH_FILE = Path.home() / ".mochi_ruler_path.json"
DEFAULT_PORT = 8765
SAMPLE_TEXT = ("陈默把剑放回鞘里，转身时听见身后的雪地里传来一声极轻的脆响。"
               "他没有回头，只是把手按在刀柄上，慢慢数到三。第三声之后，风停了。"
               "山道尽头有人提着灯笼走上来，灯罩里的火苗是绿色的，映不亮任何东西。")


def is_ruler_dir(path) -> bool:
    """有效墨尺仓库 = 目录存在且其中含 server.py。"""
    try:
        p = Path(path)
        return p.is_dir() and (p / "server.py").is_file()
    except (OSError, ValueError):
        return False


def load_saved_dir() -> str:
    """读持久化路径文件；缺失/损坏/为空一律返回 ''（不抛错）。"""
    try:
        data = json.loads(PATH_FILE.read_text(encoding="utf-8"))
        return str(data.get("ruler_dir") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def save_dir(ruler_dir: str, repo: str = RULER_REPO) -> None:
    """把解析出的墨尺路径持久化；失败只提示，不中断（运行时仍可用环境变量兜底）。"""
    payload = {"ruler_dir": str(ruler_dir), "installed_at": datetime.date.today().isoformat(),
               "repo": repo}
    try:
        PATH_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[i] 已持久化墨尺路径 → {PATH_FILE}")
    except OSError as exc:
        print(f"[!] 持久化失败（{exc}）；本次会话可改用环境变量 {KEY_ENV_DIR} 兜底")


def resolve_ruler_dir(explicit: str = "") -> str:
    """按 --dir > 环境变量 > 持久化文件 > 默认目录 的顺序找第一个有效墨尺仓库。

    返回绝对路径字符串；全都没有返回 ''。环境变量指向无效目录时打印警告但不中断。
    """
    candidates = []
    if explicit and explicit.strip():
        candidates.append(("参数 --dir", explicit.strip()))
    env_dir = os.environ.get(KEY_ENV_DIR, "").strip()
    if env_dir:
        candidates.append((f"环境变量 {KEY_ENV_DIR}", env_dir))
    saved = load_saved_dir()
    if saved:
        candidates.append((f"持久化文件 {PATH_FILE}", saved))
    candidates.append(("默认目录", str(Path.home() / ".mochi-ruler")))
    for source, path in candidates:
        if is_ruler_dir(path):
            return str(Path(path).resolve())
        if source.startswith("环境变量"):
            print(f"[!] {source}={path} 不是有效墨尺仓库（缺 server.py），继续按顺序查找")
    return ""


def server_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/", timeout=2):
            pass
        return True
    except urllib.error.HTTPError:
        return True  # 服务在，只是路径不回 200
    except (urllib.error.URLError, OSError):
        return False


def start_server(ruler_dir: str, port: int) -> None:
    """在墨尺仓库目录后台拉起 server.py（与 mochi_check.ensure_server 同款）。"""
    subprocess.Popen([sys.executable, "server.py", str(port)], cwd=ruler_dir,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def verify_install(ruler_dir: str, base_url: str, timeout: float = 15.0) -> str:
    """起服自检：探活→按需启动→POST 样章。通过返回 ''，失败返回原因。"""
    try:
        parsed_url = urllib.parse.urlsplit(base_url)
        port = parsed_url.port
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or port == 0:
            return "服务地址非法；请使用 http://127.0.0.1:8765 这样的地址"
    except ValueError as exc:
        return f"服务地址非法（{exc}）；请使用 http://127.0.0.1:8765 这样的地址"
    if not server_alive(base_url):
        if parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"} or port is None:
            return "服务无法连接；自动启动需要带端口的本机服务地址"
        try:
            start_server(ruler_dir, port)
        except OSError as exc:
            return f"自动启动墨尺服务失败：{exc}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if server_alive(base_url):
                break
            time.sleep(0.5)
        else:
            return (f"服务自检超时（{timeout:.0f}s）：请手动执行 cd {ruler_dir} && "
                    f"python server.py 后重跑 python tools/mochi_check.py 复核")
    payload = json.dumps({"text": SAMPLE_TEXT, "name": "mochi_setup_selftest"}).encode("utf-8")
    req = urllib.request.Request(base_url + "/api/analyze", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"自检请求失败（{exc}）；服务已起，可重跑 python tools/mochi_check.py 复核"
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), list) or not data["chapters"]:
        return f"自检回包异常（缺 chapters 数据）：{str(data)[:120]}"
    first = data["chapters"][0]
    score = first.get("score") if isinstance(first, dict) else None
    if not isinstance(score, dict) or score.get("total") is None:
        return f"自检回包异常（缺 chapters[0].score.total）：{str(data)[:120]}"
    return ""


def clone_repo(repo: str, dest: Path) -> str:
    """git clone --depth 1；成功返回 ''，失败返回原因（git 缺失/网络/目录占用）。"""
    try:
        done = subprocess.run(["git", "clone", "--depth", "1", repo, str(dest)],
                              capture_output=True, text=True, timeout=300,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ("未找到 git 命令。手动兜底：安装 Git 后执行\n"
                f"    git clone {repo} {dest}\n"
                f"    python tools/mochi_setup.py --dir {dest}")
    except subprocess.TimeoutExpired:
        return f"git clone 超时（300s）；网络受限时可用 --repo 指定镜像地址重试"
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "未知错误"
        return (f"git clone 失败：{tail}\n"
                f"    手动兜底：git clone {repo} <目录> 后重跑 python tools/mochi_setup.py --dir <目录>")
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="mochi_setup.py",
        description="墨尺一键安装向导：定位/clone/持久化/起服自检（装完 mochi_check.py 免环境变量）",
        epilog=f"查找顺序: --dir > {KEY_ENV_DIR} > {PATH_FILE} > ~/.mochi-ruler；"
               f"检测服务默认 http://127.0.0.1:{DEFAULT_PORT}")
    parser.add_argument("--dir", default="", help="已有墨尺仓库路径（跳过 clone）")
    parser.add_argument("--dest", default="", help=f"全新安装目标目录（默认 {Path.home() / '.mochi-ruler'}）")
    parser.add_argument("--repo", default=RULER_REPO, help=f"墨尺 git 地址（默认官方 {RULER_REPO}）")
    parser.add_argument("--no-verify", action="store_true", help="只安装不自检（不起服送样章）")
    args = parser.parse_args(argv)

    if args.dir and not is_ruler_dir(Path(args.dir).expanduser()):
        print(f"[!] --dir 指向的目录无效（缺 server.py）：{args.dir}")
        return 2

    print("═" * 30 + " 墨尺一键安装向导 " + "═" * 30)
    dest = Path(args.dest).expanduser() if args.dest.strip() else Path.home() / ".mochi-ruler"
    ruler_dir = resolve_ruler_dir(str(Path(args.dir).expanduser()) if args.dir else "")

    if not ruler_dir:
        print(f"[i] 未找到有效墨尺仓库，开始全新安装 → {dest}")
        if dest.exists() and not is_ruler_dir(dest):
            print(f"[!] 目标路径已存在且缺 server.py：{dest}\n"
                  f"    换目录：--dest <其他路径>；或已有仓库：--dir <墨尺仓库路径>")
            return 2
        err = clone_repo(args.repo, dest)
        if err:
            print(f"[!] {err}")
            return 1
        if not is_ruler_dir(dest):
            print(f"[!] 安装目录缺 server.py，仓库内容异常：{dest}")
            return 1
        ruler_dir = str(dest.resolve())
        print(f"[√] 已安装墨尺 → {ruler_dir}")
        save_dir(ruler_dir, args.repo)
    else:
        print(f"[√] 找到墨尺仓库（{ruler_dir}）")
        saved = load_saved_dir()
        if saved and Path(saved).resolve() == Path(ruler_dir):
            print(f"[i] 持久化路径已是当前目录（{PATH_FILE}）")
        else:
            save_dir(ruler_dir, args.repo)

    if args.no_verify:
        print("[i] 按要求跳过自检。验证命令：python tools/mochi_check.py \"书稿/第001章_*.md\"")
        return 0
    base_url = f"http://127.0.0.1:{DEFAULT_PORT}"
    err = verify_install(ruler_dir, base_url)
    if err:
        print(f"[!] 自检未通过：{err}")
        return 1
    print(f"[√] 自检通过：服务 {base_url} 送样章回包正常（chapters[0].score.total 在）")
    print("后续使用：python tools/mochi_check.py \"书稿/第001章_章节名.md\"（单章） / "
          "--book <项目根>（全书，报告落盘 mind/墨尺检测报告.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
