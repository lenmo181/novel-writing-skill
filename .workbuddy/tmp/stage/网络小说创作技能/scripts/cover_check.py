# -*- coding: utf-8 -*-
"""
cover_check.py — 网络小说创作技能 v7.6 封面机械质检
用法: python cover_check.py <封面图片.png|jpg> [--platform fanqie|qidian|custom]
                             [--expect WxH] [--prompt-strict]
检查项（机械可判定，语义项=文字渲染/题材/构图由 AI 看图核验，见 references/封面.md）:
  1. 文件存在、非空、可解析（PNG IHDR / JPEG SOF）
  2. 文件体积 ≥30KB（过小=占位图/损坏）
  3. 最小分辨率：宽高均 ≥600px（防马赛克封面）
  4. 宽高比与平台规格匹配（容差 ±2%）：fanqie=3:4（番茄上传 600x800），qidian=2:3，
     custom=--expect 指定
  5. 同目录同名 .prompt.txt 存在（版本化纪律；--prompt-strict 时硬卡，默认警告）
退出码: 0=通过, 1=机械项不通过, 2=输入错误
平台尺寸真源: references/常量表.md「七、封面平台尺寸」
"""
import argparse
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 与 references/常量表.md「七、封面平台尺寸」保持 1:1
PLATFORMS = {
    "fanqie":  {"ratio": 600 / 800, "upload": "600x800", "desc": "番茄 3:4（上传 600x800）"},
    "qidian":  {"ratio": 2 / 3, "upload": "按平台规格", "desc": "起点/晋江/七猫等 2:3"},
}
RATIO_TOL = 0.02      # 宽高比容差 ±2%
MIN_SIDE = 600        # 最小边长
MIN_BYTES = 30 * 1024 # 最小文件体积


def _png_sanity(data):
    """轻量 PNG 结构校验：块遍历 + CRC32 + 必须含 IDAT 与 IEND（纯标准库）。
    v7.25 新增——此前只读 IHDR 尺寸，签名+尺寸头+零填充的假图能「机械质检通过」。"""
    import zlib
    pos, has_idat, first = 8, False, True
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        end = pos + 8 + length
        if end + 4 > len(data):
            raise ValueError("PNG 块不完整（文件截断？）")
        crc = struct.unpack(">I", data[end:end + 4])[0]
        if zlib.crc32(data[pos + 4:end]) & 0xFFFFFFFF != crc:
            raise ValueError(f"PNG 块 {ctype!r} CRC 校验失败（文件损坏）")
        if first and ctype != b"IHDR":
            raise ValueError("PNG 首块不是 IHDR")
        first = False
        if ctype == b"IDAT":
            has_idat = True
        if ctype == b"IEND":
            if not has_idat:
                raise ValueError("PNG 缺少图像数据（IDAT）")
            return
        pos = end + 4
    raise ValueError("PNG 未找到 IEND 结束块（文件截断？）")


def read_size(path):
    """纯标准库读 PNG/JPEG 像素尺寸并做轻量结构校验。返回 (w, h) 或抛 ValueError。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 24:
            raise ValueError("PNG 头不完整（文件截断？）")
        if data[12:16] != b"IHDR":
            raise ValueError("PNG 缺少 IHDR")
        w, h = struct.unpack(">II", data[16:24])
        if w <= 0 or h <= 0:
            raise ValueError(f"PNG 尺寸非法 {w}x{h}")
        _png_sanity(data)
        return w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if i + 4 > len(data):
                break
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                if i + 9 > len(data):
                    break
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                if w <= 0 or h <= 0:
                    raise ValueError(f"JPEG 尺寸非法 {w}x{h}")
                return w, h
            i += 2 + seg_len
        raise ValueError("JPEG 未找到 SOF 段（文件损坏？）")
    raise ValueError("不是 PNG/JPEG 文件（当前仅支持这两种封面格式）")


def check(path, target_ratio, ratio_name, prompt_strict):
    failures, warnings = [], []
    if not os.path.isfile(path):
        print(f"[✗] 文件不存在：{path}")
        return 2
    size = os.path.getsize(path)
    if size < MIN_BYTES:
        failures.append(f"文件仅 {size/1024:.0f}KB（<{MIN_BYTES//1024}KB）——疑似占位图或损坏")
    try:
        w, h = read_size(path)
    except (ValueError, struct.error) as e:
        print(f"[✗] 无法解析图片：{e}")
        return 1 if size >= MIN_BYTES else 2
    except OSError as e:
        print(f"[✗] 输入错误：无法读取 {path}（{e}）")
        return 2

    print(f"[i] {os.path.basename(path)}：{w}x{h}（{size/1024:.0f}KB）")
    if w < MIN_SIDE or h < MIN_SIDE:
        failures.append(f"分辨率 {w}x{h} 低于下限（最小边 ≥{MIN_SIDE}）——重出更高分辨率")
    else:
        print(f"[✓] 分辨率 ≥{MIN_SIDE}px")
    ratio = w / h
    if abs(ratio - target_ratio) / target_ratio > RATIO_TOL:
        want = f"1/{1/target_ratio:.3f}" if target_ratio < 1 else f"{target_ratio:.3f}"
        failures.append(f"宽高比 {w}:{h}（{ratio:.3f}）偏离 {ratio_name}（{target_ratio:.3f}）"
                        f"超过 ±{RATIO_TOL*100:.0f}%——平台二次裁剪会切字，重出或先裁剪")
    else:
        print(f"[✓] 宽高比符合 {ratio_name}（±{RATIO_TOL*100:.0f}% 内）")

    stem, ext = os.path.splitext(path)
    prompt = stem + ".prompt.txt"
    if os.path.isfile(prompt):
        print(f"[✓] 提示词已存：{os.path.basename(prompt)}")
    elif prompt_strict:
        failures.append(f"缺少同名提示词文件 {os.path.basename(prompt)}（版本化纪律）")
    else:
        warnings.append(f"缺少同名提示词文件 {os.path.basename(prompt)}——建议补存，便于换方案重出")

    print("-" * 46)
    for wn in warnings:
        print(f"[!] 警告: {wn}")
    for fl in failures:
        print(f"[✗] 未通过: {fl}")
    if failures:
        print("结论：封面机械质检未通过——按《封面手册》修复后重跑")
        return 1
    print(f"结论：机械质检通过 ✓（语义 4 项：文字渲染/题材匹配/构图/书名安全区，AI 看图核验）"
          + (f"；另有 {len(warnings)} 项警告" if warnings else ""))
    return 0


def parse_expect(spec):
    """'600x800' -> (600, 800)；格式不对返回 None。"""
    if not re.fullmatch(r"\d+x\d+", (spec or "").lower()):
        return None
    w, h = (int(x) for x in spec.lower().split("x"))
    if w <= 0 or h <= 0:
        return None
    return w, h


def main():
    ap = argparse.ArgumentParser(
        description="封面机械质检 v7.6（尺寸/比例/体积/落盘纪律；语义项由 AI 看图核验）",
        epilog="平台比例真源=常量表·七；番茄 3:4 不是 2:3，比例不对平台二次裁剪会切书名。")
    ap.add_argument("file", help="封面图片（.png/.jpg）")
    ap.add_argument("--platform", choices=list(PLATFORMS) + ["custom"], default="fanqie",
                    help="平台口径（默认 fanqie=3:4）")
    ap.add_argument("--expect", default="", metavar="WxH",
                    help="custom 平台的目标比例，如 600x800")
    ap.add_argument("--prompt-strict", action="store_true",
                    help="缺 .prompt.txt 时按硬伤处理（默认警告）")
    args = ap.parse_args()

    if args.platform == "custom":
        dims = parse_expect(args.expect)
        if dims is None:
            print("[✗] --platform custom 必须配 --expect WxH（如 --expect 600x800）")
            return 2
        w, h = dims
        ratio_name = f"custom {w}:{h}"
        target = w / h
    else:
        p = PLATFORMS[args.platform]
        ratio_name, target = p["desc"], p["ratio"]
    sys.exit(check(args.file, target, ratio_name, args.prompt_strict))


if __name__ == "__main__":
    sys.exit(main())
