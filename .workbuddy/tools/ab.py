# -*- coding: utf-8 -*-
"""
agent-browser 可靠调用器
解决两个环境问题：
  1. npm wrapper (.cmd/.ps1) 依赖 coreutils，本机缺失 -> 直接用托管 node 跑 JS 入口
  2. shell 传中文参数乱码 -> 用 subprocess 精确按 UTF-8 传参
用法：
  python ab.py close
  python ab.py open <url> [--headed]
  python ab.py eval "<js>"
  python ab.py shot            # 截图并打印路径
  python ab.py wins            # 枚举可见窗口（诊断用）
"""
import subprocess
import sys
import os
import ctypes
import ctypes.wintypes as wt

NODE = r"C:\Users\lenmo\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
AB = r"C:\Users\lenmo\AppData\Roaming\npm\node_modules\agent-browser\bin\agent-browser.js"
CWD = r"C:\Users\lenmo\Desktop\网络小说创作技能"


def ab(*args, timeout=90):
    """调用 agent-browser，返回 (exitcode, stdout, stderr)。"""
    cmd = [NODE, AB] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run(
            cmd, cwd=CWD, env=env, timeout=timeout,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT after %ss" % timeout


def windows():
    """枚举可见顶层窗口，用于诊断浏览器窗口是否真的弹出。"""
    u = ctypes.windll.user32
    out = []

    def cb(hwnd, lp):
        if not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((hwnd, pid.value, cls.value, buf.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    u.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1

    cmd = argv[0]
    if cmd == "wins":
        ws = windows()
        print("可见窗口 %d 个:" % len(ws))
        for hwnd, pid, cls, title in ws:
            print("  hwnd=%-9s pid=%-6s %-24s %r" % (hwnd, pid, cls[:24], title[:70]))
        return 0

    code, out, err = ab(*argv)
    print("EXIT=%s" % code)
    if out.strip():
        print("--- STDOUT ---")
        print(out.strip()[:4000])
    if err.strip():
        print("--- STDERR ---")
        print(err.strip()[:2000])
    return code


if __name__ == "__main__":
    sys.exit(main())
