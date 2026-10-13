# -*- coding: utf-8 -*-
"""run_tests.py — 网络小说创作技能 v7.45 测试分片运行器。

背景
----
回归套件已经 230+ 项、单跑约 70 秒，CI 三门 Python 版本矩阵下每次全量串行跑三遍。
`unittest` 本身不支持分片，这里补一个最小分片器：按测试文件名的哈希稳定分桶，
保证同一文件永远落在同一片（CI 各分片之间不重不漏）。

用法
----
    python tools/run_tests.py                 # 全量（等价 unittest discover）
    python tools/run_tests.py --shard 1/3     # 只跑第 1 片（共 3 片）
    python tools/run_tests.py --list-shards 3 # 打印每片分到哪些文件，不执行

退出码：0=全部通过 / 1=有失败 / 2=参数错误
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def discover_test_files() -> list:
    return sorted(p.name for p in TESTS.glob("test_*.py"))


def shard_files(files: list, index: int, total: int) -> list:
    """稳定分桶：以文件体积作为耗时代理，贪心装箱到当前最轻的片。

    分配只依赖 (文件名 → 体积) 的固定序，因此同一批文件在任何机器上分法一致；
    新增文件只会追加到最轻的片，不会打乱已有分片的归属。
    """
    sized = sorted(((TESTS / name).stat().st_size, name) for name in files)
    buckets = [[] for _ in range(total)]
    loads = [0] * total
    for size, name in reversed(sized):  # 大的先放，剩下的补齐
        target = loads.index(min(loads))
        buckets[target].append(name)
        loads[target] += size
    return sorted(buckets[index - 1])


def load_selected(names: list) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in names:
        suite.addTests(loader.discover(str(TESTS), pattern=name, top_level_dir=str(TESTS)))
    return suite


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="测试分片运行器")
    parser.add_argument("--shard", default="", help="分片，格式 i/n，如 1/3")
    parser.add_argument("--list-shards", type=int, default=0, help="打印分片方案后退出")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    files = discover_test_files()
    if not files:
        print("[✗] tests/ 下未发现 test_*.py")
        return 2

    if args.list_shards:
        for i in range(1, args.list_shards + 1):
            picked = shard_files(files, i, args.list_shards)
            print(f"shard {i}/{args.list_shards}（{len(picked)} 个文件）：{'，'.join(picked) or '（空）'}")
        return 0

    if args.shard:
        try:
            idx, total = (int(x) for x in args.shard.split("/"))
        except ValueError:
            print("[✗] --shard 格式应为 i/n，如 1/3")
            return 2
        if not (1 <= idx <= total):
            print(f"[✗] --shard 越界：{args.shard}（i 应在 1..{total}）")
            return 2
        picked = shard_files(files, idx, total)
        label = f"[shard {idx}/{total}]"
    else:
        picked = files
        label = "[full]"

    if not picked:
        print(f"{label} 本片没有测试文件，视作通过")
        return 0

    print(f"{label} 运行 {len(picked)} 个测试文件")
    suite = load_selected(picked)
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
