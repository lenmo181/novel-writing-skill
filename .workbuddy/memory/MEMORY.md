# 项目长期记忆 · 网络小说创作技能

## 技能包约定

- 文件夹名「网络小说创作技能」为稳定名，**版本号只写在 SKILL.md 头部与 `versions/`**，不改目录名。
- 本地运行时目录：`tools/`（源目录保持原样，不动）。
- 上架包构建副本中该目录会改名为 `scripts/`（WorkBuddy 开放平台规范目录）。

## 上架包构建约定

- 构建 = `python .workbuddy/tools/build_market_zip.py`，输出 `dist/网络小说创作技能_v<VER>_market.zip`。
- **源目录零改动**：所有脱敏/改名/补字段只发生在 `.workbuddy/tmp/stage/` 构建副本里。
- 硬性排除：`.git/`、`.workbuddy/`、`.v2c/`、`.video_agent/`、`__pycache__/`、`out/`。
- `out/` 永不进包——里面是热榜取证的**第三方作品正文**与本作者作品看板截图，公开分发有版权与首发风险。
- 个人绝对路径（`C:\Users\lenmo\...`）一律不得出现在包内，替换为 `~/novels/`、`~/.workbuddy/skills/...`。
- 上架前必跑：`scan_pack.py`（体检）+ `verify_pack.py`（ZIP 结构 / 脚本可执行性）+ 包内 `scripts/check_refs.py`（相对引用零悬空）。

## 平台提交信息（当前）

- 市场展示名称：网络小说创作技能 · 作者：豫晨 · 分类：writing · 版本：7.23.0
- 开放平台：https://open.workbuddy.cn （发布管理 → 技能 → 创建）
