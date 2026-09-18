# -*- coding: utf-8 -*-
"""清理 .workbuddy/tmp 残留（送回收站）并输出 .workbuddy 现状"""
import ctypes, os
from ctypes import wintypes

ROOT = r"C:\Users\lenmo\Desktop\网络小说创作技能"
TMP = os.path.join(ROOT, ".workbuddy", "tmp")

print("=== .workbuddy 现状 ===")
WB = os.path.join(ROOT, ".workbuddy")
for dp, dns, fns in os.walk(WB):
    for f in fns:
        p = os.path.join(dp, f)
        print("  %8.1f KB  %s" % (os.path.getsize(p) / 1024, os.path.relpath(p, ROOT)))
    for d in dns:
        print("  [DIR ]      %s" % os.path.relpath(os.path.join(dp, d), ROOT))

if not os.path.isdir(TMP):
    print("\ntmp 已不存在")
    raise SystemExit(0)

leftovers = [os.path.join(TMP, x) for x in os.listdir(TMP)]
print("\n=== tmp 残留 %d 项，送回收站 ===" % len(leftovers))
for p in leftovers:
    print("  " + os.path.relpath(p, ROOT))

FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION = 3, 0x40, 0x10
FOF_SILENT, FOF_NOERRORUI, FOF_NOCONFIRMMKDIR = 0x4, 0x400, 0x200


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def recycle(paths):
    src = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = src
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_NOCONFIRMMKDIR
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))


if leftovers:
    r = recycle(leftovers)
    print("\n返回码: %d" % r)
    for p in leftovers:
        print("  %-40s %s" % (os.path.basename(p), "!! 仍存在" if os.path.exists(p) else "已移除"))

# 空目录直接删除（回收站里空目录无意义）
if os.path.isdir(TMP) and not os.listdir(TMP):
    try:
        os.rmdir(TMP)
        print("\ntmp 空目录已删除")
    except OSError as e:
        print("\ntmp 目录删除失败: %s" % e)

print("\n=== .workbuddy 最终 ===")
for dp, dns, fns in os.walk(WB):
    for f in fns:
        p = os.path.join(dp, f)
        print("  %8.1f KB  %s" % (os.path.getsize(p) / 1024, os.path.relpath(p, ROOT)))
