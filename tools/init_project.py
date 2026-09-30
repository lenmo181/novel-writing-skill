# -*- coding: utf-8 -*-
"""创建可直接续写的网络小说项目骨架（v7.33）。

只创建缺失文件，默认不覆盖已有内容；适合新书初始化，也适合给空目录补齐
标准档案。模板使用 UTF-8 和标准库，生成后可立即交给 project_audit 检查。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from config import SKILL_VERSION, default_project_root


GENERATED_MARKER = "由 tools/init_project.py 生成"


def safe_project_name(title: str) -> str:
    """把书名转换成适合目录名的短名称。"""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title.strip())
    value = re.sub(r"\s+", " ", value).strip(" .")
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.I):
        value = "_" + value
    return value or "新小说"


def _header(title: str, section: str) -> str:
    return f"# {section}\n\n> {GENERATED_MARKER}；书名：{title}。\n\n"


def project_files(title: str, genre: str, platform: str, target_words: str, today: str) -> dict[str, str]:
    """返回项目初始化文件，不访问磁盘。"""
    title = title.strip() or "未命名小说"
    genre = genre.strip() or "待补充"
    platform = platform.strip() or "待补充"
    target_words = target_words.strip() or "待补充"
    files: dict[str, str] = {
        "README.md": (
            f"# {title}\n\n{GENERATED_MARKER}。\n\n"
            f"- 题材：{genre}\n- 平台：{platform}\n- 预计字数：{target_words}\n"
            f"- 创建日期：{today}\n\n"
            "## 最短路径\n\n"
            "1. 补完 `设定/` 和 `大纲/` 中的待补充字段。\n"
            "2. 写完章节后运行 `python <技能目录>/tools/gen_index.py .`。\n"
            "3. 用 `python <技能目录>/tools/project_health.py .` 检查项目状态。\n"
        ),
        "项目元数据.json": json.dumps({
            "schema_version": 1,
            "generated_by": f"init_project.py v{SKILL_VERSION}",
            "title": title,
            "genre": genre,
            "platform": platform,
            "target_words": target_words,
            "created_date": today,
        }, ensure_ascii=False, indent=2) + "\n",
        "大纲/总纲.md": _header(title, "总纲") + "## 一句话梗概\n\n[待补充]\n\n## 主角终点\n\n[待补充]\n\n## 结局与核心高潮\n\n[待补充]\n",
        "大纲/卷纲.md": _header(title, "卷纲") + "| 卷号 | 卷名 | 起止章 | 核心冲突 | 卷末变化 |\n|---|---|---|---|---|\n| 1 | [待补充] | 1-[待补充] | [待补充] | [待补充] |\n",
        "大纲/章纲.md": _header(title, "章纲") + "| 章号 | 章节名 | 节奏类型 | 本章目标 | 冲突/代价 | 章末钩子类型与指纹 | 伏笔编号 |\n|---|---|---|---|---|---|---|\n| 1 | [待补充] | [待补充] | [待补充] | [待补充] | [待补充] | [待补充] |\n",
        "大纲/场景纲.md": _header(title, "场景纲") + "| 章号 | 场景 | 视角 | 地点/时间 | 目标 | 阻碍 | 转折/不可逆变化 | 离开钩子 |\n|---|---|---|---|---|---|---|---|\n| 1 | 1 | [待补充] | [待补充] | [待补充] | [待补充] | [待补充] | [待补充] |\n",
        "设定/世界观.md": _header(title, "世界观") + "## 时空与社会\n\n[待补充]\n\n## 核心规则\n\n[待补充]\n\n## 规则边界与代价\n\n[待补充]\n",
        "设定/角色.md": _header(title, "角色设定") + "## 主角（姓名待补充）\n\n- 别名：无\n- 目标：[待补充]\n- 恐惧/缺口：[待补充]\n- 能力与代价：[待补充]\n- 关系：[待补充]\n",
        "设定/文风样本.md": _header(title, "文风样本") + "## 风格定位\n\n[待补充]\n\n## 样本文本\n\n[可选；无样本不阻塞写作]\n\n## 反例黑名单\n\n[待补充]\n",
        "mind/角色状态快照.md": _header(title, "角色状态快照") + "## 主角（姓名待补充）\n\n- 别名：[待补充]\n- 首次出场章：[待补充]\n- 位置：[待补充]\n- 持有：[待补充]\n- 状态：[待补充]\n- 情绪：[待补充]\n- 知情：[待补充]\n- 最后出场：[待补充]\n",
        "mind/锚点日志.md": _header(title, "锚点日志") + "| 章节 | 类型 | 内容 | 涉及角色 |\n|---|---|---|---|\n",
        "mind/伏笔追踪表.md": _header(title, "伏笔追踪表") + "| 编号 | 伏笔内容 | 埋设章 | 预计回收章 | Tier | 状态 |\n|---|---|---|---|---|---|\n",
        "mind/时间线.md": _header(title, "时间线") + "| 章节 | 故事内时间 | 跨度说明 | 读者已知变化 |\n|---|---|---|---|\n",
        "mind/章节目录.md": _header(title, "章节目录") + "| 章号 | 标题 | 字数 | 节奏类型 | 校验结果 | 完成日期 |\n|---|---|---:|---|---|---|\n\n当前进度：已完成至第0章，下一章为第1章\n",
        "mind/剧情走向锁定.md": _header(title, "剧情走向锁定") + "| 日期 | 决策内容 | 来源（用户指定/正文已写死） |\n|---|---|---|\n",
        "mind/作者记忆.md": _header(title, "作者记忆") + "一次性要求只执行；小说事实写入设定；推断偏好标待确认；显式覆盖保留旧记录。\n\n尚无已确认的作者偏好。\n",
        ".story-review/state.md": (
            f"# 审查断点状态\n\n> {GENERATED_MARKER}。\n\n"
            f"- 审查范围：尚未开始\n- 审查日期：{today}\n\n"
            "## 开放项\n\n| 编号 | 级别 | 类别 | 位置 | 问题 | 处置状态（待办/已修/搁置） |\n|---|---|---|---|---|---|\n\n"
            "## 继承的伏笔开放项\n\n暂无。\n\n## 下批起点\n\n- 下一批审查从第1章开始\n"
        ),
        "mind/回顾/README.md": f"# 单章回顾\n\n{GENERATED_MARKER}。写完每章后保存为 `第XXX章回顾.md`。\n",
        "书稿/.gitkeep": "",
        "剧本/.gitkeep": "",
    }
    return files


def init_project(target: Path, title: str, genre: str = "待补充", platform: str = "待补充",
                 target_words: str = "待补充", dry_run: bool = False) -> dict:
    """创建项目并返回机器可读结果。"""
    if not title.strip() or any("\n" in value or "\r" in value for value in (title, genre, platform, target_words)):
        raise ValueError("书名必填；元数据字段使用单行文本")
    target = Path(target).expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise NotADirectoryError(str(target))
    today = date.today().isoformat()
    files = project_files(title, genre, platform, target_words, today)
    # 所有路径预检完成后才写入，防止同名文件占用目录时留下半套骨架。
    for rel in files:
        path = target / rel
        if target not in path.resolve().parents:
            raise ValueError(f"项目路径指向根目录以外：{rel}")
        if path.exists() and not path.is_file():
            raise IsADirectoryError(str(path))
        for parent in path.parents:
            if parent == target:
                break
            if parent.exists() and not parent.is_dir():
                raise NotADirectoryError(str(parent))
    created: list[str] = []
    skipped: list[str] = []
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = target / rel
        if path.exists():
            skipped.append(rel)
            continue
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            # 排他创建：预检后若另一个进程创建了同名文件，也保留它。
            try:
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(content)
            except FileExistsError:
                skipped.append(rel)
                continue
        created.append(rel)
    return {
        "version": SKILL_VERSION,
        "root": str(target.resolve()),
        "title": title.strip() or "未命名小说",
        "dry_run": dry_run,
        "created": created,
        "skipped": skipped,
        "file_count": len(files),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"创建长篇网络小说项目骨架 v{SKILL_VERSION}（短篇使用短篇模式模板）")
    parser.add_argument("project", nargs="?", default="", help="项目根目录；省略时使用默认小说工作区/书名")
    parser.add_argument("--title", required=True, help="书名")
    parser.add_argument("--genre", default="待补充", help="题材")
    parser.add_argument("--platform", default="待补充", help="目标平台")
    parser.add_argument("--target-words", default="待补充", help="预计字数，例如80万字")
    parser.add_argument("--dry-run", action="store_true", help="只列出将创建的文件，不写盘")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    target = Path(args.project).expanduser() if args.project.strip() else default_project_root() / safe_project_name(args.title)
    try:
        report = init_project(target, args.title, args.genre, args.platform, args.target_words,
                              args.dry_run)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[✗] 初始化失败：{exc}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        verb = "将创建" if args.dry_run else "已创建"
        print(f"[✓] {verb}项目：{report['root']}")
        print(f"[i] 文件：{report['file_count']}；新增 {len(report['created'])}；保留 {len(report['skipped'])}")
        for rel in report["created"]:
            print(f"  + {rel}")
        if report["skipped"]:
            print("[i] 已有文件保留，未覆盖：" + "、".join(report["skipped"][:8]))
        print("下一步：补完设定与大纲后运行 project_health.py，再开始写第1章。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
