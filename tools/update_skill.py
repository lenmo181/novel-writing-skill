#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查并安全更新网络小说创作技能（v7.50）。

默认只检查 SkillHub 版本；只有明确使用 --update/--auto 且确认后才替换本地技能。
更新只影响 Codex 技能目录，不触碰用户的小说项目目录。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Tuple

try:
    from config import SKILLHUB_DOWNLOAD_URL, SKILLHUB_SLUG, SKILL_VERSION as _SKILL_VERSION
except ImportError:  # 允许直接复制脚本后仍能给出可用默认值
    SKILLHUB_DOWNLOAD_URL = (
        "https://api.skillhub.cn/api/v1/download?slug=@user_cd8383ec/web-novel-writing"
    )
    SKILLHUB_SLUG = "@user_cd8383ec/web-novel-writing"
    # 仅在脚本被单独复制、无法导入 config.py 时使用；与当前发布版本保持同步。
    _SKILL_VERSION = "7.49"

# v7.47：UA 从 config 读版本——此前两处硬编码 "…updater/7.29"，已漂移 17 个
# 版本且不在 bump 登记点位，永远同步不到
USER_AGENT = "network-novel-writing-skill-updater/%s" % _SKILL_VERSION


SKILL_NAME = "网络小说创作技能"
VERSION_RE = re.compile(r"(?<!\d)v?(\d+)\.(\d+)(?:\.(\d+))?(?!\d)")
REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class Release:
    version: Tuple[int, int, int]
    version_text: str
    download_url: str
    filename: str


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """让版本检查读取 302 的文件名和最终下载地址，而不是下载 ZIP。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_version(value: str) -> Tuple[int, int, int]:
    match = VERSION_RE.search(value or "")
    if not match:
        raise ValueError("无法解析版本号：%s" % value)
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def version_text(version: Tuple[int, int, int], preserve_patch: bool = True) -> str:
    if preserve_patch or version[2]:
        return ".".join(str(part) for part in version)
    return "%d.%d" % version[:2]


def default_destination() -> Path:
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    skill_root = Path(__file__).resolve().parents[1]
    skills_dir = (base / "skills").resolve()
    if skills_dir in skill_root.parents and (skill_root / "SKILL.md").is_file():
        return skill_root
    slug_install = skills_dir / SKILLHUB_SLUG
    if (slug_install / "SKILL.md").is_file():
        return slug_install
    return base / "skills" / SKILL_NAME


def default_backup_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skill-update-backups"


def read_local_version(root: Path) -> Tuple[int, int, int]:
    skill = root / "SKILL.md"
    config = root / Path(__file__).resolve().parent.name / "config.py"
    for path, pattern in (
        (skill, r"版本[^\n]*?v(\d+\.\d+(?:\.\d+)?)"),
        (config, r"SKILL_VERSION\s*=\s*[\"'](\d+\.\d+(?:\.\d+)?)[\"']"),
        (root / "scripts" / "config.py", r"SKILL_VERSION\s*=\s*[\"'](\d+\.\d+(?:\.\d+)?)[\"']"),
    ):
        if path.exists():
            match = re.search(pattern, path.read_text(encoding="utf-8", errors="replace"))
            if match:
                return parse_version(match.group(1))
    raise FileNotFoundError("未找到可识别的本地技能版本：%s" % root)


def _filename_from_header(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", value, re.I)
    if match:
        return urllib.parse.unquote(match.group(1).strip().strip('"'))
    match = re.search(r"filename\s*=\s*\"?([^;\"]+)\"?", value, re.I)
    return match.group(1).strip() if match else ""


def _release_from_headers(headers, source_url: str, location: str = "") -> Release:
    filename = _filename_from_header(headers.get("Content-Disposition", ""))
    final_url = urllib.parse.urljoin(source_url, location) if location else source_url
    version_source = " ".join((filename, final_url))
    version = parse_version(version_source)
    if not filename:
        filename = "web-novel-writing-%s.zip" % version_text(version)
    return Release(version, version_text(version), final_url, Path(filename).name)


def fetch_latest(download_url: str, timeout: int = 20) -> Release:
    request = urllib.request.Request(
        download_url,
        headers={"User-Agent": USER_AGENT},
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        # v7.47：从 config 读版本——此前硬编码 "…updater/7.29"，已漂移 17 个
        # 版本且不在 bump 登记点位，永远同步不到
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code not in REDIRECT_CODES:
            raise
        return _release_from_headers(exc.headers, download_url, exc.headers.get("Location", ""))
    with response:
        return _release_from_headers(response.headers, download_url)


def _safe_relative(name: str, prefix: Optional[str] = None) -> Optional[Path]:
    # v7.47：先规范化反斜杠——此前 PurePosixPath 把 Windows 风格
    # "..\..\evil.py"/"D:\evil.py" 视为单个部件，名义检查全部失效，
    # 唯一防线是 extract_zip 的 resolve 围栏（单点，无防御纵深）
    raw = PurePosixPath(name.replace("\\", "/"))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("ZIP 含不安全路径：%s" % name)
    parts = raw.parts
    if prefix and parts and parts[0] == prefix:
        parts = parts[1:]
    if not parts:
        return None
    return Path(*parts)


def _archive_prefix(infos: Iterable[zipfile.ZipInfo]) -> Optional[str]:
    files = [PurePosixPath(info.filename) for info in infos if not info.is_dir()]
    if PurePosixPath("SKILL.md") in files:
        return None
    tops = {path.parts[0] for path in files if path.parts}
    if len(tops) == 1:
        top = next(iter(tops))
        if PurePosixPath(top, "SKILL.md") in files:
            return top
    return None


def extract_zip(zip_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        prefix = _archive_prefix(infos)
        for info in infos:
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError("ZIP 含符号链接，拒绝解压：%s" % info.filename)
            relative = _safe_relative(info.filename, prefix)
            if relative is None:
                continue
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError("ZIP 路径越界：%s" % info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    candidate = destination
    if not (candidate / "SKILL.md").exists():
        children = [path for path in destination.iterdir() if path.is_dir()]
        matches = [path for path in children if (path / "SKILL.md").exists()]
        if len(matches) == 1:
            candidate = matches[0]
    config_dirs = {"scripts", Path(__file__).resolve().parent.name}
    if not (candidate / "SKILL.md").is_file() or not any((candidate / name / "config.py").is_file() for name in config_dirs):
        raise ValueError("ZIP 不是有效的网络小说创作技能包：缺少 SKILL.md 或运行时 config.py")
    return candidate


def download_release(release: Release, destination: Path, timeout: int = 60) -> Path:
    request = urllib.request.Request(
        release.download_url,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as sink:
        shutil.copyfileobj(response, sink, length=1024 * 256)
    return destination


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _clear_tree(root: Path) -> None:
    if not root.exists():
        return
    for item in root.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def backup_current(source: Path, backup_root: Path) -> Optional[Path]:
    if not source.exists():
        return None
    backup_root.mkdir(parents=True, exist_ok=True)
    try:
        current = version_text(read_local_version(source))
    except (FileNotFoundError, ValueError):
        current = "unknown"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_root / ("%s-v%s-%s" % (SKILL_NAME, current, stamp))
    # v7.47：秒级 stamp 在同一秒内两次 --force（CI 重试）→ copytree 抛
    # FileExistsError 更新失败且无法重试；追加 -2/-3 后缀
    n = 2
    while target.exists():
        target = backup_root / ("%s-v%s-%s-%d" % (SKILL_NAME, current, stamp, n))
        n += 1
    shutil.copytree(source, target)
    return target


def replace_skill(candidate: Path, destination: Path, backup_root: Path) -> Optional[Path]:
    """v7.47：同分区 rename 交换（近原子）——此前 _clear_tree 全删 + _copy_tree
    逐文件复制，进程在此期间被 kill/断电/蓝屏时 destination 处于半清空状态：
    备份完好但没有任何自动恢复机制，且下次运行只报"未找到本地版本"退出。
    备份回滚只覆盖"异常路径"，不覆盖"进程死亡路径"，这是原设计最大缺口。
    """
    backup = backup_current(destination, backup_root)
    staging = destination.with_name(destination.name + ".staging-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    retired = destination.with_name(destination.name + ".old-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        if staging.exists():
            _clear_tree(staging)
        _copy_tree(candidate, staging)
        read_local_version(staging)
        # 近原子交换：旧目录改名退场 → 新目录改名上场；任一步失败即反向换回
        if destination.exists():
            os.replace(destination, retired)
        try:
            os.replace(staging, destination)
        except Exception:
            if retired.exists():
                os.replace(retired, destination)  # 反向换回
            raise
        if retired.exists():
            shutil.rmtree(retired, ignore_errors=True)
        return backup
    except Exception as orig_err:
        # 清理半成品 staging； retired/destination 状态由上面保证至少其一完好
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        rollback_err = None
        try:
            if retired.exists() and not destination.exists():
                os.replace(retired, destination)
            if not destination.exists() and backup:
                _clear_tree(destination)
                _copy_tree(backup, destination)
        except Exception as rb:
            rollback_err = rb
        if rollback_err is not None:
            print(f"[!] 回滚失败：{rollback_err}", file=sys.stderr)
            if backup:
                print(f"[i] 备份完好，可手工恢复：复制 {backup} → {destination}", file=sys.stderr)
        raise orig_err


def check_or_update(args: argparse.Namespace) -> int:
    destination = Path(args.destination).expanduser() if args.destination else default_destination()
    download_url = args.download_url
    local = read_local_version(destination)
    latest = fetch_latest(download_url, timeout=args.timeout)
    available = latest.version > local
    result = {
        "localVersion": version_text(local),
        "latestVersion": latest.version_text,
        "updateAvailable": available,
        "localAhead": local > latest.version,
        "downloadUrl": latest.download_url,
        "destination": str(destination),
    }

    should_apply = args.update or args.auto
    if not should_apply or (not available and not args.force):
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            state = "有新版本" if available else ("本地版本较新" if local > latest.version else "已是最新")
            print("[update] 本地 v%s；SkillHub v%s；%s" % (version_text(local), latest.version_text, state))
        return 2 if available and not should_apply else 0

    if not args.auto and not args.yes:
        # v7.47：非交互环境（stdin 关闭/重定向/CI/管道）input() 抛 EOFError，
        # 此前不在 main 的 except 元组里 → 裸 traceback。无人值守请用 --yes/--auto
        if not sys.stdin.isatty():
            print("[update] 非交互环境（stdin 不可读）：请使用 --yes 或 --auto 参数")
            return 2
        try:
            answer = input("检测到 v%s，是否更新并备份当前版本？[y/N] " % latest.version_text).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("[update] 无交互输入，按取消处理")
            return 0
        if answer not in {"y", "yes"}:
            print("[update] 用户取消，未修改本地技能")
            return 0

    with tempfile.TemporaryDirectory(prefix="network-novel-skill-update-") as work:
        work_root = Path(work)
        zip_path = work_root / latest.filename
        stage = work_root / "stage"
        download_release(latest, zip_path, timeout=args.timeout)
        candidate = extract_zip(zip_path, stage)
        candidate_version = read_local_version(candidate)
        if candidate_version < latest.version:
            raise ValueError(
                "下载包内部版本 v%s 低于平台版本 v%s"
                % (version_text(candidate_version), latest.version_text)
            )
        backup = replace_skill(candidate, destination, Path(args.backup_dir).expanduser())

    result.update({"updated": True, "backup": str(backup) if backup else None})
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("[update] 已更新到 v%s" % latest.version_text)
        if backup:
            print("[update] 旧版本备份：%s" % backup)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查并安全更新网络小说创作技能")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查版本（默认）")
    mode.add_argument("--update", action="store_true", help="检查后更新，默认会询问确认")
    mode.add_argument("--auto", action="store_true", help="检查后自动更新，无需交互确认")
    parser.add_argument("--yes", action="store_true", help="跳过确认，仅与 --update 一起使用")
    parser.add_argument("--force", action="store_true", help="即使版本相同也重新下载并安装")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--timeout", type=int, default=20, help="网络超时秒数，默认 20")
    parser.add_argument("--destination", default=str(default_destination()), help="Codex 技能目录")
    parser.add_argument("--backup-dir", default=str(default_backup_dir()), help="备份目录")
    parser.add_argument(
        "--download-url",
        default=SKILLHUB_DOWNLOAD_URL,
        help="SkillHub 下载接口",
    )
    return parser


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return check_or_update(args)
    # v7.47：补 http.client.HTTPException——下载中断抛的 IncompleteRead 是
    # HTTPException 子类而非 OSError/URLError，此前逃出捕获元组裸 traceback
    # （大 zip 下载到 90% 断流是常见场景）
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile,
            http.client.HTTPException, EOFError, KeyboardInterrupt) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print("[update] 失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
