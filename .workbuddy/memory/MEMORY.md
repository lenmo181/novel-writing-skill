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

## SkillHub 发布路线（v7.45.0 起走通）

- 市场名 `网络小说创作技能` · slug `web-novel-writing` · 命名空间 `@user_cd8383ec` · 作者 豫晨 · 分类 writing。
- **发布走 CLI（推荐，可接 CI），不要走网页上传表单**：网页表单的「选择 zip 文件」是系统原生文件框，浏览器自动化无法操作。
- CLI = Python 脚本（`skills_store_cli.py`），Windows 可直接跑。安装：`curl -fsSL https://skillhub.cn/install/install.sh | bash -s -- --cli-only`（拉腾讯云 COS 的 `latest.tar.gz`）。
- 认证：`python skills_store_cli.py login --key skh_xxx --host https://api.skillhub.cn`（先 `auth whoami` 校验）。发布端点 `POST https://api.skillhub.cn/api/v1/community/skills/publish`，Bearer + multipart。
- **发布前必过三关**：
  1. SKILL.md frontmatter 需 `slug` + `displayName`（驼峰），构建包内是 `name`/`display_name`，发布前需补。
  2. 包内**不得含无扩展名文件**（`LICENSE`/`NOTICE` 会被 `400 不允许的文件类型` 拒），许可证改由 frontmatter `license` 声明；`.ps1`/`.md`/`.py`/`.json` 可。
  3. API Token 在 `skillhub.cn/dashboard/keys` 创建（`skh_` 开头，只显示一次）——用弹窗「复制 Token」→ `Get-Clipboard` 读取。
- 发布后状态「安全审核中」为正常，审核通过自动上架。`--dry-run` 可做本地预检。

## 平台提交信息（当前）

- 市场展示名称：网络小说创作技能 · 作者：豫晨 · 分类：writing · **版本：7.45.0**（已提交，安全审核中，skillId 205643）
- 开放平台：https://open.workbuddy.cn
- SkillHub 技能页：https://skillhub.cn/skills/user_cd8383ec/web-novel-writing
