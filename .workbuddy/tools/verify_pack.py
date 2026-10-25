# -*- coding: utf-8 -*-
"""校验实际 SkillHub ZIP：结构、版本、许可证和解压后的运行时诊断。"""
import argparse
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "网络小说创作技能"


def verify(zip_path, version):
    if not zip_path.is_file():
        raise ValueError(f"发布包不存在：{zip_path}")
    if zip_path.stat().st_size > 3 * 1024 * 1024:
        raise ValueError("发布包超过 3MB")
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if not names or len(names) != len(set(names)):
            raise ValueError("ZIP 为空或含重复条目")
        for name in names:
            parts = PurePosixPath(name).parts
            base = PurePosixPath(name).name
            if (not parts or parts[0] != SKILL_NAME or ".." in parts or "\\" in name
                    or any(part.startswith(".") or part == "__pycache__" for part in parts)
                    or name.endswith((".pyc", ".pyo", ".bak", ".tmp"))):  # v7.47：原子写安全网产物
                raise ValueError(f"非法 ZIP 条目：{name}")
            if base and "." not in base:
                raise ValueError(f"非法 ZIP 条目（无扩展名，SkillHub 会拒绝）：{name}")
        required = ("SKILL.md", "README.md", "SECURITY.md", "CONTRIBUTING.md",
                    "scripts/config.py", "scripts/sync_skill.ps1", "scripts/mochi_setup.py",
                    "schemas/chapter_semantic_review.schema.json", "schemas/chapter_readiness.schema.json",
                    "schemas/full_review_queue.schema.json", "schemas/project_metadata.schema.json",
                    "versions/CHANGELOG.md")
        missing = [name for name in required if f"{SKILL_NAME}/{name}" not in names]
        if missing:
            raise ValueError("包内缺失：" + ", ".join(missing))
        skill = archive.read(f"{SKILL_NAME}/SKILL.md").decode("utf-8-sig")
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", skill, re.S)
        if not match:
            raise ValueError("SKILL.md frontmatter 非法")
        fields = {}
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError("frontmatter 字段格式非法")
            if key in fields:
                raise ValueError(f"frontmatter 重复字段：{key}")
            fields[key] = value.strip()
        if fields.get("name") != "web-novel-writing" or fields.get("version") != version + ".0":
            raise ValueError("包内技能名称或版本与源配置不一致")
        # SkillHub CLI 发布前置校验：LICENSE/NOTICE 因无扩展名已被排除，许可证改由 frontmatter 声明
        if not fields.get("license"):
            raise ValueError("包内缺少 frontmatter license 声明")
        if fields.get("slug") != "web-novel-writing":
            raise ValueError("包内缺少 CLI 发布所需的 slug（且须与技能名一致）")
        if not fields.get("displayName"):
            raise ValueError("包内缺少 CLI 发布所需的 displayName")
        package_config = archive.read(f"{SKILL_NAME}/scripts/config.py").decode("utf-8")
        if not re.search(r'^SKILL_VERSION = ["\']' + re.escape(version) + r'["\']\s*$', package_config, re.M):
            raise ValueError("包内 config.py 版本不一致")
        print(f"ZIP 结构与版本通过：{len(names)} 个文件，v{version}.0", flush=True)
        with tempfile.TemporaryDirectory(prefix="novel-package-audit-") as temp:
            archive.extractall(temp)
            extracted = Path(temp) / SKILL_NAME
            for script in ("doctor.py", "lint_skill.py", "check_refs.py", "eval_skill.py"):
                result = subprocess.run([sys.executable, str(extracted / "scripts" / script)],
                                        cwd=extracted, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=120)
                print(f"{script}: exit={result.returncode}", flush=True)
                if result.returncode:
                    print(result.stdout + result.stderr)
                    raise ValueError(f"最终 ZIP 解压后 {script} 失败")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="校验指定 ZIP；默认当前版本 dist 包")
    args = parser.parse_args(argv)
    config = (ROOT / "tools" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'^SKILL_VERSION = ["\'](\d+\.\d+)["\']', config, re.M)
    if not match:
        parser.error("源 config.py 缺少 SKILL_VERSION")
    version = match.group(1)
    zip_path = args.zip or ROOT / "dist" / f"{SKILL_NAME}_v{version}.0_skillhub.zip"
    try:
        verify(zip_path, version)
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(f"发布包校验失败：{exc}", file=sys.stderr)
        return 1
    print("最终 ZIP 校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
