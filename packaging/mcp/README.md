# 网络小说创作技能 · MCP Server

把「网络小说创作技能」里的**只读机械校验脚本**暴露成 MCP 工具，
让任意 MCP 宿主（Claude Desktop / Claude Code / Cursor / WorkBuddy / Cline / Windsurf …）
在写小说时能直接调用硬卡校验与交付闸门。

- 协议：MCP over **stdio**，JSON-RPC 2.0（`2025-06-18`）
- 依赖：**纯 Python 标准库，零第三方依赖**
- 安全：**只读白名单**——写盘类脚本（`write_chapter` / `bump_version` / `init_project` 等）被显式拒绝，绝不改动你的书稿

---

## 安装

### 方式一：uvx（推荐，无需预装技能）

```bash
uvx web-novel-writing-mcp
```

wheel 内**自带完整技能包**（`SKILL.md` + `scripts/` + `references/`），
因此开箱即用，`doctor` 等技能自检类工具也能直接跑通。

### 方式二：pip

```bash
pip install web-novel-writing-mcp
web-novel-writing-mcp
```

### 方式三：源码直跑（技能包已 checkout）

```bash
python packaging/mcp/server.py
```

源码模式下脚本目录自动解析为仓库的 `tools/`。

---

## 宿主配置

### Claude Code

```bash
claude mcp add novel-writing -- uvx web-novel-writing-mcp
```

### Claude Desktop

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "novel-writing": {
      "command": "uvx",
      "args": ["web-novel-writing-mcp"],
      "env": {
        "NOVEL_PROJECT_ROOT": "D:/novels"
      }
    }
  }
}
```

### Cursor

编辑 `~/.cursor/mcp.json`（或项目内 `.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "novel-writing": {
      "command": "uvx",
      "args": ["web-novel-writing-mcp"]
    }
  }
}
```

### WorkBuddy

编辑 `~/.workbuddy/mcp.json`：

```json
{
  "mcpServers": {
    "novel-writing": {
      "command": "uvx",
      "args": ["web-novel-writing-mcp"]
    }
  }
}
```

> 写入后 MCP 不会自动生效：在连接器管理页右上角的「自定义连接器」入口点「信任」即可启用。

### Cline / Windsurf / 其他

同上，只需 `command = uvx`、`args = ["web-novel-writing-mcp"]`。

---

## 工具清单

| 工具 | 作用 | 关键参数 |
| --- | --- | --- |
| `check_chapter` | 单章 13 项机械硬卡（字数 / 格式 / 对话占比 / AI 味 / 文字墙 / 冲突值）。退出码 1 = 有硬伤，禁止交付 | `path` |
| `chapter_readiness` | 章节交付 Gate：校验第 14–30 项语义证据是否齐全（需 `mind/审校/第XXX章审校.json` 带 `status` + `evidence`） | `project_root`, `chapter`, `full?` |
| `doctor` | 技能安装自检：目录骨架 / 必需文件 / 版本真源 / 脚本语法 / 相对引用 / 目录树登记完整性 | — |
| `list_skill_tools` | 列出当前可调用的只读脚本与脚本目录位置 | — |
| `run_skill_tool` | 通用入口：运行白名单内任一脚本，返回退出码与输出 | `script`, `args?` |

### 只读白名单（19 个）

```
check_chapter.py        chapter_readiness.py    conflict_score.py
continuity_check.py     review_skeleton.py      project_audit.py
project_health.py       grep_consistency.py     entity_index.py
research_audit.py       retention_check.py      cover_check.py
script_check.py         chapter_diff.py         check_refs.py
lint_skill.py           eval_skill.py           doctor.py
export_assistant_txt.py
```

白名单外的脚本一律拒绝执行（返回 `isError: true`）。

---

## 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `NOVEL_SKILL_ROOT` | 外部技能包根目录；设置后覆盖 wheel 自带技能包 | wheel 内 `_skill/` |
| `NOVEL_SKILL_SCRIPTS` | 直接指定脚本目录（优先于上面两项的目录推导） | 自动解析 |
| `NOVEL_PROJECT_ROOT` | 用户小说项目根目录（脚本默认值来源） | `~/.codex/workspace/novels` |

**脚本目录解析顺序**：
`NOVEL_SKILL_SCRIPTS` → wheel 内 `_skill/{tools,scripts}` → 技能根 `{tools,scripts}`。
源仓库为 `tools/`，上架包内为 `scripts/`，两者都兼容。

---

## 目录

```
packaging/mcp/
├── server.py     # 服务器实现（唯一真源；wheel 构建时复制进包）
├── server.json   # MCP Registry 清单（publisher 用）
└── README.md     # 本文件
```

构建与自检：

```bash
python packaging/pypi/build_wheel.py   # 产出 wheel 并自动安装 + 握手 + 跑 doctor
```
