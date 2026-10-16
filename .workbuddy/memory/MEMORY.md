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

- **已上架渠道**：SkillHub（v7.45/7.46 安全审核中）、Qoder 能力市场、**魔搭 ModelScope**（已上线）、**awesomeskills.dev**（已收录）。
- **魔搭 ModelScope（已走通，可全自动）**：端点 `https://www.modelscope.cn/openapi/v1`——注意 `www.modelscope.cn/api/v1/users/me` 会 400，**必须走 `/openapi/v1`**。三步 = `POST /files/upload`（`-F type=skill`）取 `data.id` → `POST /skills`（owner/skill_name/display_name/skill_file/category）→ `PATCH /skills/{owner}/{name}/settings`（description/source_url/license/category/tags 生效）。打包用 `.workbuddy/tools/build_modelscope_zip.py`（要求 zip 根目录恰好 1 个 SKILL.md）。技能页：https://www.modelscope.cn/skills/lenmo181/web-novel-writing
  - **边界**：`logo_url` **只收 URL 不收上传返回的 id**；`locales` / `description_en` 字段返回 success 但**静默忽略**，英文描述只能进网页控制台补；tags 回读会自动加 `category:` / `license:` / `custom_tag:` 前缀。
- **GitHub 同步**：沙箱代理**屏蔽 github.com 但放行 api.github.com**；`git push` 必失败 → 走 **Git Data API 原子提交**（blob→tree→commit→ref，脚本 `.workbuddy/tmp/gh_push.py`）。**PNG 与它的目录树登记必须同一提交**，否则 CI 的 `doctor --package-smoke` 必红。
- **WorkBuddy 开放平台**：被「深度合成-AI创作」类目卡死（该类目仅**企业认证**可用），个人账号走不通，已搁置。
- **Claude directory**：需**付费 Claude 计划**，用户暂无 → 跳过。
- **TRAE 技能市场**：**未开放自助上架**（官方论坛明确回复），只能邮件 `feedback@mail.trae.cn` 申请。
- **扣子 Coze 技能商店**：个人版可上架，但技能须在**扣子编程侧创建**（提示词/工作流形态，非传 SKILL.md），需先申请「技能上架资质」+ 备 **3 个精选案例**（带链接与图片）。
- **海外渠道需英文物料**：仓库根已加 `README.en.md`，并登记进 `references/目录结构.md`。
- ⚠️ **新增文件必须登记目录树**：`doctor.py` 会拦「未登记文件」，登记真源 = `references/目录结构.md`（v7.44 起自 SKILL.md 外置）。**但 `packaging/` 与 `assets/` 例外**（见下节）。

## 分发封装约定（2026-10-16 立）

- `packaging/` = **构建期分发封装**，与 `.workbuddy/`、`dist/`、`out/` 同类：**不随技能包分发**。
  - `packaging/mcp/`：MCP Server（`server.py` + `server.json` + `README.md`）
  - `packaging/pypi/`：`build_wheel.py`（纯标准库 wheel 构建器）+ `README.md`
  - `packaging/dify/`：Dify 插件骨架 + `bundle_skill.py`
- **doctor 豁免必须双向**：`doctor.py` 的 `_tree_excluded()` 同时过滤**磁盘侧**（`on_disk`）与**登记侧**（`registered`）。只豁免一侧 → 被构建排除却仍登记的文件会变成「登记但不存在」幽灵条目，**已发布的包会直接报「需要修复」**。`TREE_EXCLUDED_PARTS` 含 `packaging`/`assets`，`TREE_EXCLUDED_FILES` 含 `icon_512.png`。三态（仓库/上架包/wheel）应统一为 **91/91**。
- `check_refs.py` 的 `SKIP_DIRS` 同样含 `packaging`——其文档里的 `tools/xxx.py` 是"包内相对路径"写法，会与本仓库 `tools/` 同名冲突。
- **PyPI wheel 必须打包「整个技能包」**：放在 `web_novel_writing_mcp/_skill/`。原因有二——① `config.py` 的 `skill_root()` = `parents[1]`，脚本必须在 `_skill/tools/`；② `doctor.py`/`lint_skill.py`/`eval_skill.py` 需要完整技能骨架才能通过。
- **构建器用纯标准库**（`zipfile`+`hashlib`），环境里没有 `build`/`setuptools`，且与本技能「零第三方依赖」约束一致。构建器自带自检：`pip install --target` → MCP 握手 → 调 `doctor`。
- **构建命令**：`python packaging/pypi/build_wheel.py`（→ `dist/web_novel_writing_mcp-<ver>-py3-none-any.whl`）；`python packaging/dify/bundle_skill.py`。
- **只读白名单是双侧共享的**：MCP 的 `READONLY_TOOLS` 与 Dify `helper.py` 的同一集合（19 个），写盘脚本（`write_chapter`/`bump_version`/`init_project` 等）一律拒绝。
- **Dify 工具以「正文文本」为输入**：Dify 插件跑在**远端沙箱**，读不到用户本地磁盘；沙箱内落临时文件后跑脚本，返回即销毁。MCP 则走本地 stdio 可传路径——两者互补。
- 生成物不入库：`.gitignore` 已加 `packaging/pypi/build_pkg/`、`packaging/dify/_skill/`。

## 发布渠道状态（2026-10-16）

| 渠道 | 状态 |
|---|---|
| SkillHub / Qoder / 魔搭 / awesomeskills.dev | ✅ 已通 |
| PyPI | ✅ wheel 已构建+自检通过 🔑 等 Token |
| MCP 注册表 | ✅ Server 已完成+实测 🔑 需 PyPI 先上架（`identifier` 必须是真包）+ GitHub OIDC |
| Dify | ✅ 骨架已产出 🔑 等账号提 PR |
| 扣子 / TRAE | 📝 等资质申请 / 邮件 |
| 元器 / 文心 | 📝 建议先做 1 个最小可用验证 |
