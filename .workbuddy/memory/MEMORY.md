# 项目长期记忆 · 网络小说创作技能

## 技能包约定

- 文件夹名「网络小说创作技能」为稳定名，**版本号只写在 SKILL.md 头部与 `versions/`**，不改目录名。
- 本地运行时目录：`tools/`（源目录保持原样，不动）。
- 上架包构建副本中该目录会改名为 `scripts/`（WorkBuddy 开放平台规范目录）。

## 上架包构建约定

- 构建 = `python .workbuddy/tools/build_market_zip.py`，输出 `dist/网络小说创作技能_v<VER>_skillhub.zip`。
- **v7.46 起构建已内置 SkillHub 契约**：包内 SKILL.md 自动补 `slug`/`displayName`/`summary`/`license`(Apache-2.0)，并跳过无扩展名文件（LICENSE/NOTICE）→ dist 包可直接 `skillhub publish <zip>`，无需人工改动。`verify_pack.py` 已成可发布性门禁（拦无扩展名条目 + 查 slug/displayName/license）。
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

- 市场展示名称：网络小说创作技能 · 作者：豫晨 · 分类：writing · **版本：7.46.0**（已提交，安全审核中，skillId 205643）
- 开放平台：https://open.workbuddy.cn
- SkillHub 技能页：https://skillhub.cn/skills/user_cd8383ec/web-novel-writing

## 多平台发布路线（2026-10-16 起）

- **已上架渠道**：SkillHub（v7.45/7.46 安全审核中）、Qoder 能力市场、**魔搭 ModelScope**。
- **魔搭 ModelScope（已走通，可全自动）**：端点 `https://www.modelscope.cn/openapi/v1`——注意 `www.modelscope.cn/api/v1/users/me` 会 400，**必须走 `/openapi/v1`**。三步 = `POST /files/upload`（`-F type=skill`）取 `data.id` → `POST /skills`（owner/skill_name/display_name/skill_file/category）→ `PATCH /skills/{owner}/{name}/settings`（description/source_url/license/category/tags 生效）。打包用 `.workbuddy/tools/build_modelscope_zip.py`（要求 zip 根目录恰好 1 个 SKILL.md）。技能页：https://www.modelscope.cn/skills/lenmo181/web-novel-writing
  - **边界**：`logo_url` **只收 URL 不收上传返回的 id**；`locales` / `description_en` 字段返回 success 但**静默忽略**，英文描述只能进网页控制台补；tags 回读会自动加 `category:` / `license:` / `custom_tag:` 前缀。
- **WorkBuddy 开放平台**：被「深度合成-AI创作」类目卡死（该类目仅**企业认证**可用），个人账号走不通，已搁置。
- **Claude directory**：需**付费 Claude 计划**，用户暂无 → 跳过。
- **TRAE 技能市场**：**未开放自助上架**（官方论坛明确回复），只能邮件 `feedback@mail.trae.cn` 申请。
- **扣子 Coze 技能商店**：个人版可上架，但技能须在**扣子编程侧创建**（提示词/工作流形态，非传 SKILL.md），需先申请「技能上架资质」+ 备 **3 个精选案例**（带链接与图片）。
- **Tier C（需改形态）**：Dify（`.difypkg` + 英文 README + 隐私政策 + PR 到 `langgenius/dify-plugins`）、MCP 注册表（封装 MCP Server）、元器/文心（智能体 Bot）。
- **海外渠道需英文物料**：仓库根已加 `README.en.md`，并登记进 `references/目录结构.md`。
- ⚠️ **新增文件必须登记目录树**：`doctor.py` 会拦「未登记文件」，登记真源 = `references/目录结构.md`（v7.44 起自 SKILL.md 外置）。
