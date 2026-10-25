# 网络小说创作技能

[![CI](https://github.com/lenmo181/novel-writing-skill/actions/workflows/verify.yml/badge.svg)](https://github.com/lenmo181/novel-writing-skill/actions/workflows/verify.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

> **当前版本：v7.50**（2026-10-25）
> 一个面向 ZCode / Codex / Claude Code 等 AI 编码助手的网文创作工程化技能：把“会写小说”变成可以初始化、检查、修复、复检、回滚和发布的工程流程。

它不是单纯的提示词合集，也不是小说生成器。核心目标是建立一套**可追踪、可验证、可回归**的小说生产系统。

---

## v7.50 本轮升级重点

- **同类小说研究**：新增 `tools/similar_novels.py`，按题材从 TTNovels 选最多 3 本公开作品，读取简介和章节标题生成结构卡，24 小时缓存并自动接入写章上下文。
- **原创性护栏**：`--check-draft` 检测连续 12 字原句和高重合片段风险；报告明确禁止复用专名、单本章节顺序和大段正文。
- **隐私与版权边界**：初始化项目新增 `研究/同类小说配置.json`，联网默认关闭；工具不抓取、不保存章节正文，只有用户明确允许联网后才读取公开页面。
- **视角约束**：默认第三人称、单主角限知；必要时才在场景边界少量切换角色视角，并保持每个场景单一限知。

## v7.49 本轮升级重点

- **事实台账**：新增 `mind/事实台账.md` + `tools/fact_ledger.py`——先登记后写、到期必兑、数字事实优先登记；位置化事实语义（`chapter_before:12` 等），只读核验。
- **证据引文不可篡改**：语义审校 `evidence` 升为 `{text, quote, offset}`，服务端逐字比对正文——AI 编造的"原文摘录"过不了交付门；`review_skeleton.py --find-quote` 反查偏移。
- **伏笔到期三层提醒**：必须回收 / 已超期 / 近期待回收，已回收伏笔不催债。
- **量化 AI 味指标**：「不是A是B」≤2 处/章、单一意象 ≤1 次/千字（警告级）。
- **发布元数据统一**：MCP Registry 清单、英文 README 与更新器回退版本纳入治理；更新器不再向用户展示停留在 v7.46 的旧版本。
- **数字事实阈值校正**：`FACT_LEDGER_MAX_PER_CHAPTER` 按单章统计，跨章重复不再误报。
- **分发构建编码修复**：PyPI wheel 与 Dify 打包器统一 UTF-8 终端输出，中文 Windows 不会在打印 ✓ 时假失败。
- **修一个 P0 崩溃**：期待线台账含"活跃"条目时 `continuity_check.py` 必 NameError，连带中断交付 Gate——本版修复。

## v7.48 本轮升级重点

- **看板从「体检单」变「驾驶舱」**：新增写作分析分区——写作热力日历、月度产出、质量矩阵（字数 × 朱雀分）、节奏结构、人物出场频次、AI 味走势；总览重做为 6 张 KPI + 统一「待处理」预警箱（节奏 / 沉睡伏笔 / 字数不足 / 断更 / 检测缺口一次列全）。
- **伏笔有了时间轴**：伏笔页新增健康环与埋设跨度条（埋设章 → 回收章），埋设 ≥30 章仍未回收的自动列「沉睡」预警。
- **查章不再翻下拉**：Ctrl/⌘+K 命令面板按章号、章节名、分区名模糊跳转；深色主题一键切换并记忆，`?theme=dark` 可固定观感。
- **图表全部手写 SVG**：零外部依赖、单文件离线可用；折线纵轴与柱图上限改按数据自适应，千章自动按桶聚合。
- 顺手修掉四处会误导的显示：未来日期导致的负数「断更 N 天」、短章书柱图贴底、高分书走势被压平、月度柱撑满卡片。

## v7.47 本轮升级重点

- **MCP Server 不再被单行坏消息杀死**：非对象 JSON 行（batch 数组/字符串/数字）此前让 `req.get` 抛 AttributeError 穿透主循环，一行输入即会话死亡；stdio 同步做 UTF-8 重配置——中文 Windows 下输出 `✓/✗` 不再炸进程、中文路径不再变乱码。未知工具按 MCP 规范返回 `-32602`。
- **只读通道恢复“只读”语义**：白名单脚本经 `run_skill_tool` 透传 `--out/--force` 即可任意路径写盘的漏洞收口（参数黑名单）；默认即写盘的 `export_assistant_txt` 移出白名单。Dify 侧同款黑名单 + 临时目录整树清理 + 环境变量优先级对齐。
- **13 项机械硬卡排雷**：回忆标记子串双计数不再误杀正常开篇（单短语从 3 计到 1）；标题识别补全角/中文数字/空格/`#` 前缀（第 13 项校验与开篇闸门不再静默跳过）；`## 小节标题` 不再泄漏进正文；「睡意」不再误判醒来式开场；拟声词 8 处转义错码改汉字字面量。
- **修复流水线复活**：机械候选不再被审稿队列 loc 混同去重吞掉（`apply-mechanical` 此前几乎永远空转）；`verify` 补 `--no-write` 不再静默重写队列；机械修复成果以 `auto_fixed` 登记进队列，二审回归记忆自此覆盖。
- **状态文件韧性**：审稿队列/改版落盘全部改原子写 + `.bak`；畸形队列结构校验不再裸崩；重复章号不再使 P0 章节重复检测静默失效；`issue_key` 数字归一化令 fixed 状态继承稳定。
- **改版工具加固**：`--from` 格式校验防静默损坏版本台账；verify 子进程补 UTF-8（中文 Windows 不再假绿）；两阶段原子落盘消除混合版本状态；`SERVER_VERSION` 纳入登记点位。

## v7.46 本轮升级重点

- **发布包直接可被 SkillHub CLI 发布**：`build_market_zip.py` 现在在包内 `SKILL.md` 的 frontmatter 补出 CLI 必需的驼峰字段 `slug` / `displayName`（并补 `summary` / `license`），同时把无扩展名的 `LICENSE` / `NOTICE` 排除出包——SkillHub 服务端对无扩展名文件直接 `400 不允许的文件类型`。结果是 `dist/*_skillhub.zip` 无需任何人工改动即可 `skillhub publish <zip>` 一条命令发布，为接 CI 自动发版铺平。
- **发布包校验成为可发布性门禁**：`verify_pack.py` 新增「无扩展名条目即拦截」和 `slug` / `displayName` / `license` 必需字段校验；此前它反而硬要求 `LICENSE` / `NOTICE`，与 SkillHub 服务端契约正面冲突。同步移除了包内 `doctor.py` 对这两个文件的硬要求，消除解压后自检的「缺少 LICENSE, NOTICE」误报。
- 许可证改由 frontmatter `license: Apache-2.0` 声明（仓库根目录仍保留 `LICENSE` / `NOTICE` 供源码分发）。

## v7.45 本轮升级重点

- **章节索引与增量扫描 `tools/chapter_index.py`**（超长篇地基）：元数据（章号 / 标题 / 字数 / sha256）落盘到 `mind/.index/chapters.json`，以 `(mtime_ns, size)` 为失效判据——没动过的章直接复用缓存，只有改过的才重新读盘。三条纪律：索引是缓存不是事实（删掉自动重建、结果一致）；不缓存正文（避免与 `书稿/` 双写）；判据用 mtime+size 而非每次重算 sha256（否则等于重新读盘，失去增量意义）。
- `full_review` 与 `context_pack` 的元数据改走索引：查章号从「每章 glob 一次 `书稿/`」变成 O(1) 查表，取最近 N 章不再有 stat 风暴；索引不可用时自动回退原全量扫描路径，行为不变。
- **上下文预算控制器**：此前只有单文件上限、没有总量闸门，长篇后期上下文会线性膨胀。现在新增总预算 24000 字符，按角色权重切分（当前章 3.0 倍权重 + 25% 保底，预算再紧也不会把正在写的这一章挤没），报告新增 `budget` 块（used / per_role / limits / truncated_files），`--max-total 0` 可关闭。
- **测试分片 `tools/run_tests.py`**：`--shard i/n` 按测试文件体积贪心装箱（比哈希取模均衡：实测 5/8/7 而非 5/10/5），分配稳定、不重不漏；CI 矩阵加 3 分片，墙钟时间约降为 1/3。
- 修复三处工程债：README 亮点段此前被改版工具「标题版本号 +1、内容不动」的规则错位（v7.44 内容挂了 v7.45 标题，本版改为 insert_before 保留历史段，并由 lint 增设占位闸门）；`doctor` 的冒烟清单是手工表，连续三版漏登记新工具、冒烟数虚高为「全过」（本版补齐 6 个工具至 39/39，并新增清单登记闸门——未登记即失败）；`release_check --strict` 下 tag 检查失败项的 KeyError。

## v7.44 本轮升级重点

- **主文件瘦身**：`SKILL.md` 从 **89KB / 868 行降到 35KB / 277 行**（-61%）。写作铁律早在 v7.40 就外置到 `references/写作铁律.md`，主文件却仍保留整份副本——这次清掉重复，主文件只留路由中枢：frontmatter、全局配置、模式路由表、快速开始、失败码与交付闸门、写章节执行流程，其余全部按需路由。
- 新增三本外置手册：`references/目录结构.md`（doctor 目录树登记真源）、`references/指令速查.md`、`references/30项校验明细.md`。`doctor.py` 改为优先读 `目录结构.md`，缺失时回退 SKILL.md，兼容旧安装。
- **审校骨架生成器 `tools/review_skeleton.py`**：按 schema 一次生成第14-30项骨架，项名取自核心校验映射（不另备清单），自动算正文 `chapter_sha256`；默认 `status=revise`，**骨架绝不会误通过 Gate**。
- **语义弱证据档 `weak`**：AI 语义复核不可用时可用机械证据兜底，Gate 不卡死，但 `delivery_ready=false`、报告标 `semantic_strength=weak` 并列出具体项——可继续写，不可当正式交付结论。
- **规则观察期到期机制**：`lint_skill.py` 对「候选/实验态且距上次裁定 ≥3 版」的规则自动点名，逼出显式裁定。本期处置：RB-027 废弃（11 版无校准数据、从未独立硬卡），RB-031 延长观察期（v7.45 前须给终局结论）。
- **日期真源闸门**：此前版本号有 lint 守着、日期没有。现在 `config.py` 是唯一真源，`SKILL.md` / `README.md` / `CHANGELOG.md` 必须与之逐字一致，`lint_skill.py` 本地即可拦截漂移。
- **测试不再复制日期**：`tests/release_meta.py` 把「断言日期等于某值」换成「四真源互相印证」，改版只改真源，测试永不失联。
- **发布链门禁**：`release_check.py` 新增「HEAD 是否落在 v* tag 上」（默认警告，`--strict` 判失败）与「dist/ 是否有同号发布包」（判失败）。CI 增加 tag 触发。
- **历史补齐**：v7.41 / v7.42 落成提交并打 `v7.42.0` tag，该版本发布包从此可从源码重建。

## 这是什么

网络小说创作技能把小说创作拆成几个可以重复执行的层：

**创作层 → 档案层 → 检查层 → 修复层 → 回归层 → 发布层**

- **创作层**：长篇、短篇、短剧、扫榜、拆文、旧书导入、审校、去 AI 味、封面。
- **同类小说研究**：写章前可按题材从 TTNovels 选最多 3 本公开作品，只读取简介与章节标题生成结构卡，并对草稿做连续片段重合提示；不抓取或保存章节正文，联网需项目配置和用户授权。
- **档案层**：世界观、角色、时间线、伏笔、章节目录、剧情锁定、作者记忆、单章回顾。
- **检查层**：章节机械校验、连续性、结构、全文审稿、AI 味、项目健康。
- **修复层**：备份/快照、差异检查、机械修复、修复任务包、修复状态。
- **回归层**：修复后二审、回归检测、规则台账、评测场景、CI。
- **发布层**：lint、doctor、release check、GitHub Actions。

### 核心原则

> **先有事实，再有修改；先有证据，再有规则；修完必须复检。**

诊断工具的写入边界见工具表；全文审稿默认写入报告和队列，可用 `--no-write` 完全只读。涉及正文写入的流程必须明确写入边界，并提供备份或快照路径。

---

## 核心能力

### 1. 30 项校验体系

30 项校验分为机械检查和 AI 语义检查，并明确区分：

- **硬卡**：失败后禁止直接交付。
- **警告**：提示风险，由作者/AI 结合上下文判断。
- **题材例外**：通过书格/参数覆盖部分非底线规则。
- **交付底线**：例如 A 级禁言词、严重格式残留等，不因为题材而静默豁免。

30 项校验的机器注册入口：

[references/核心校验映射.md](references/核心校验映射.md)

规则生命周期与证据治理：

[references/规则台账.md](references/规则台账.md)

运行时手册版本真源：

[references/版本台账.md](references/版本台账.md)

### 2. 长篇连载工程

项目初始化后可以持续维护：

- 总纲 / 卷纲 / 章纲 / 场景纲
- 世界观 / 角色 / 文风样本
- 角色状态快照
- 伏笔追踪
- 时间线
- 章节目录
- 剧情走向锁定
- 作者记忆
- 单章回顾
- 上下文包
- 实体别名/关系/出场台账

目标是让“下一章怎么写”建立在项目事实之上，而不是完全依赖当前对话窗口。

### 3. 全文审稿 → 修复 → 二审

全文审稿由 tools/full_review.py 统一编排诊断：

正文 → 全文扫描 → P0-P3 → 问题队列 → 修复任务 → 重新检查 → 二审 → 回归

目前重点覆盖：

- 章节断档
- 已亡角色再次出现
- 节奏类型连续
- 章节长度异常
- 相邻章节重复/换皮
- 伏笔沉睡
- 对话比例异常
- 跨章回归问题

修复队列使用明确状态：

open → fixed / auto_fixed / wont_fix

问题重新出现时可以进入：

reopened

### 4. 修复不是“直接改正文”

当前工程把“发现问题”和“修改正文”分离：

- full_review.py：负责发现和登记问题。
- repair_runner.py：负责维护修复状态。
- repair_orchestrator.py：把问题转成修复任务并组织“快照 → 修复 → 复检”。
- fix_said_tags.py：执行已有机械修复规则。
- chapter_diff.py：判断修改幅度和大删风险。
- snapshot_project.py：在大修前建立项目快照。

> **自动化可以加速机械修复，但不能默认用整章重写替代局部修复。**

### 5. AI 味检测

项目提供两级检测：

- check_chapter.py --ai-lite：零外部服务的本地粗测。
- mochi_check.py：本地墨尺检测（首次用 `python tools/mochi_setup.py` 一键安装，免环境变量）。
- zhuque_check.py：可选第三方线上检测。

线上检测属于**外部数据传输**，必须显式允许后才发送正文。

项目不会把“AI 分数”当作唯一质量标准；检测结果需要结合语言、情绪、对话、节奏、结构、视角、解释、重复等维度进行定向修改。

### 6. 章节交付 Gate

chapter_readiness.py 把多个检查收敛为一个章节级结果，默认验证第14-30项语义证据。`--with-semantic` 保持兼容；草稿检查用 `--skip-semantic`，其成功退出仅代表工程检查通过，不代表可交付：

- 单章机械校验
- 项目健康
- 连续性
- 上下文构建
- 可选全文审稿

输出 JSON 后可以被 AI Agent、脚本或 CI 继续消费。

### 7. 项目记忆与可追溯上下文

context_pack.py：生成带 SHA-256 来源摘要的上下文包。

memory_search.py：从项目内的 mind/、大纲/、设定/、.story-review/ 检索长期事实。

> **写作上下文不是“模型脑内记忆”，而是项目文件中的可回读事实。**

### 8. 审计日志与安全快照

audit_log.py 提供追加式 JSONL 审计日志，并使用 SHA-256 链记录：

- 动作
- 对象
- 状态
- 时间
- 前一条日志的 hash
- 当前记录 hash

可用于检查日志是否被改写。

snapshot_project.py 用于大修前快照与 manifest。

---

## 3 分钟开始使用

### 第一步：安装

对于 Codex，建议把技能目录放入：

~/.codex/skills/网络小说创作技能/

仓库提供 PowerShell 同步脚本：

```powershell
powershell -ExecutionPolicy Bypass -File tools/sync_skill.ps1
```

其他宿主环境可以按实际技能目录复制/同步。

### 第二步：初始化一本新书

```bash
python tools/init_project.py "<项目根>" --title "雾城拾荒者" --genre "都市悬疑" --platform "番茄" --target-words "80万字"
```

生成项目骨架后，补充设定/、大纲/、mind/ 以及首章正文。

### 第三步：检查环境

```bash
python tools/doctor.py
python tools/doctor.py --runtime-smoke --package-smoke
```

### 第四步：写完一章后先检查

```bash
python tools/check_chapter.py "书稿/第001章_章节名.md"
python tools/check_chapter.py "书稿/第001章_章节名.md" --ai-lite
```

退出码：

- 0：机械校验通过。
- 1：存在硬伤，不建议直接交付。
- 2：输入或环境错误。

### 第五步：做项目级检查

```bash
python tools/project_audit.py "<项目根>"
python tools/continuity_check.py "<项目根>"
python tools/project_health.py "<项目根>"
python tools/grep_consistency.py "<项目根>"
```

### 第六步：做全文审稿

```bash
python tools/full_review.py "<项目根>" --json
python tools/full_review.py "<项目根>" --strict --json
```

报告默认落盘：mind/全文审稿报告.md

问题队列默认落盘：mind/全文审稿队列.json

### 第七步：章节 30 项语义证据

正式交付前：

```bash
python tools/chapter_readiness.py "<项目根>" 42 --with-semantic --full --json
```

语义记录：`mind/审校/第042章审校.json`，覆盖第14-30项，每项至少 `status + evidence`，并绑定当前正文 `chapter_sha256`；正文一旦变化，旧证据自动失效。

### 第八步：修复和二审

```bash
python tools/repair_orchestrator.py "<项目根>" prepare --json
python tools/repair_orchestrator.py "<项目根>" apply-mechanical --apply --json
python tools/repair_orchestrator.py "<项目根>" verify --full --json
```

---

## 推荐生产流水线

```text
初始化
  ↓
设定 / 大纲
  ↓
写章
  ↓
check_chapter
  ↓
continuity + project_health
  ↓
full_review
  ↓
修复任务包
  ↓
snapshot
  ↓
局部修复
  ↓
chapter_diff
  ↓
check_chapter
  ↓
full_review 二审
  ↓
release_check
  ↓
交付
```

持续写作时，每完成一章都重复其中的局部闭环，而不是等到几十章后才一次性检查。

---

## 工具速查

| 工具 | 作用 | 默认写入 |
|---|---|---|
| check_chapter.py | 单章机械校验 | 否 |
| full_review.py | 全文诊断、问题队列、二审 | 写入 mind/报告与队列，不改正文 |
| chapter_readiness.py | 章节交付 Gate | 否 |
| repair_runner.py | 修复状态管理 | 只改队列 |
| repair_orchestrator.py | 修复计划、机械修复编排、复检 | 默认不写正文 |
| fix_said_tags.py | 对话引导语等机械修复 | 是，带备份机制 |
| project_audit.py | 项目骨架/章节/目录体检 | 否 |
| project_health.py | 汇总项目健康 | 否 |
| continuity_check.py | 角色/伏笔/时间线连续性 | 否 |
| grep_consistency.py | 典型档案-正文矛盾扫描 | 否 |
| context_pack.py | 可追溯上下文包 | 生成报告时写文件 |
| memory_search.py | 项目长期记忆检索 | 否 |
| entity_index.py | 角色别名/关系/出场台账 | 可按 --out 写 |
| chapter_diff.py | 修改差异和大删风险 | 否 |
| snapshot_project.py | 项目快照 | 创建快照 |
| gen_index.py | 章节目录生成/更新 | 是 |
| visualize.py | 离线可视化看板/阅读器（十分区 + 写作分析洞察 + 深色主题） | 生成 HTML |
| conflict_score.py | 冲突值计算 | 否 |
| retention_check.py | 留存/结构建议分析 | 否 |
| script_check.py | 剧本机械质检 | 否 |
| cover_check.py | 封面机械质检 | 否 |
| zhuque_check.py | 可选线上 AI 文本检测 | 外部服务调用 |
| mochi_check.py | 本地 AI 味检测 | 可生成报告 |
| eval_skill.py | 17 个评测场景矩阵检查 | 否 |
| lint_skill.py | 规则/版本/常量/映射治理 | 否 |
| doctor.py | 安装/语法/引用/运行冒烟 | 否 |
| release_check.py | 发布前综合预检 | 否 |
| update_skill.py | SkillHub 检查/更新/备份/回滚 | 修改技能安装副本 |
| audit_log.py | 项目审计日志 | 追加日志 |
| research_audit.py | 研究来源台账检查 | 否 |
| similar_novels.py | TTNovels 同类小说结构研究与原创性护栏 | 是（需明确联网授权） |

完整入口说明见：[references/工具选择.md](references/工具选择.md)

---

## 项目文件结构

```text
项目/
├── README.md
├── 项目元数据.json
├── 书稿/
├── 大纲/
├── 设定/
├── mind/
│   ├── 章节目录.md
│   ├── 角色状态快照.md
│   ├── 伏笔追踪表.md
│   ├── 时间线.md
│   ├── 剧情走向锁定.md
│   ├── 作者记忆.md
│   └── 回顾/
├── .story-review/
│   ├── state.md
│   └── audit.jsonl
├── 剧本/
├── 研究/
│   ├── 同类小说配置.json
│   └── 同类小说研究.md/json
└── 封面/
```

设定/、大纲/、mind/ 是项目事实的主要承载层；正文只是其中一个数据源。

---

## 文档导航

| 需求 | 文档 |
|---|---|
| 第一次使用 | [快速开始](references/快速开始.md) |
| 不知道该运行哪个工具 | [工具选择](references/工具选择.md) |
| 长篇连载 | [长篇模式](references/长篇模式.md) |
| 短篇 | [短篇模式](references/短篇模式.md) |
| 短剧 | [短剧剧本](references/短剧剧本.md) |
| 接手旧书 | [导入旧书](references/导入旧书.md) |
| 审校/改稿 | [审校](references/审校.md) |
| 去 AI 味 | [去AI味](references/去AI味.md) |
| 节奏与钩子 | [节奏与结构](references/节奏与结构.md) |
| 连载记忆 | [连载记忆](references/连载记忆.md) |
| 规则与证据 | [规则台账](references/规则台账.md) |
| 操作示例 | [操作范例](references/操作范例.md) |
| 模式路由 | [模式操作卡](references/模式操作卡.md) |
| 评测 | [评测场景](references/评测场景.md) / [评测量表](references/评测量表.md) |
| 安全 | [SECURITY.md](SECURITY.md) |
| 贡献 | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## 规则治理

项目把“规则”当成工程资产管理，而不是永久不变的真理。

新增或修改规则时，需要同步：

研究来源 → 规则台账 → 核心校验映射 → 执行器 → 回归测试 → 版本台账 → 发布检查

规则至少记录：来源、最近验证、验证广度、证据等级、当前状态、落点、执行工具、对应测试。

发布前由 lint_skill.py 检查关键治理链是否断裂。

---

## 评测和 CI

仓库自带：

- 16 个自然语言评测场景。
- Python 3.10 / 3.12 / 3.13 CI 矩阵。
- Python 语法编译检查。
- skill lint。
- 引用完整性检查。
- 评测矩阵校验。
- doctor 冒烟。
- 全量回归测试。

本地可以运行：

```bash
python tools/lint_skill.py
python tools/check_refs.py
python tools/eval_skill.py --json
python tools/doctor.py --runtime-smoke --package-smoke
python -m unittest discover -s tests -p "test_*.py"
```

发布前：

```bash
python tools/release_check.py --tests
```

CI 配置：[.github/workflows/verify.yml](.github/workflows/verify.yml)

---

## 安全边界

### 默认不上传正文

大多数工具是本地文件检查，不需要网络。

### 第三方 AI 检测

使用 zhuque_check.py 等线上服务时，正文会离开本机。必须明确授权，并自行确认服务商的数据保留和使用政策。

### API Key

不要把以下内容提交到仓库：

- API Key
- 密码
- Cookie / Token
- 未公开小说正文
- 个人敏感信息

### 自动写入

正文或档案写入应尽量遵循：先快照/备份 → 再修改 → 做差异检查 → 再做章节检查 → 最后做全文二审。

---

## 许可证

本项目使用 **Apache License 2.0（Apache-2.0）**。

许可证文件：[LICENSE](LICENSE)

归因说明：[NOTICE](NOTICE)

第三方代码、数据、模型、示例、外部服务及引用资料仍受各自许可证或服务条款约束。

---

## 贡献

贡献前请阅读：[CONTRIBUTING.md](CONTRIBUTING.md)

提交新规则时，优先补齐：问题 → 证据 → 规则 → 执行器 → 测试 → 文档 → 发布。

不建议只增加“更严格的数字阈值”。如果某规则存在题材差异，应优先考虑证据等级、题材例外、警告/硬卡分层、人工确认点和可回归测试。

---

## 常见问题

### 为什么没有一个“万能生成小说”按钮？

因为本项目重点解决长期连载和工程可控性，而不是把整本小说生成任务变成一次性黑箱调用。

### 为什么很多检查只是警告？

因为文学自然度、节奏、人物表现存在明显题材差异，不能把所有软指标都变成机械硬卡。

### 为什么修复工具默认不整章重写？

因为大范围重写可能破坏已经正确的伏笔、人物状态和作者决定。工程默认倾向于“局部修复 + 差异检查 + 二审”。

### 为什么安装后还要运行 doctor？

因为“文件存在”不等于“运行时可用”。doctor 会检查结构、版本、语法、引用和运行级入口。

更多故障排查：[references/常见问题.md](references/常见问题.md)

---

## 项目定位

这个项目适合：

- 使用 AI 编码助手进行网文创作的人。
- 需要长期维护 10 万字、50 万字、100 万字以上项目的人。
- 需要把续写、审校、去 AI 味、连续性从聊天行为变成固定流程的人。
- 需要把规则、测试和版本治理放进 Git 的创作者/开发者。

它不试图替代作者。

> **更接近一套小说项目的工程操作系统 + 质量检查工具链 + AI 协作协议。**

---

## 版本

程序版本真源：[tools/config.py](tools/config.py)

当前版本：**v7.50**

历史版本：[versions/](versions/)

运行时手册版本：[references/版本台账.md](references/版本台账.md)

最近版本重点：

- **v7.50**：新增 TTNovels 三本同类小说结构研究、缓存和草稿原创性重合护栏，写章前可自动接入。
- **v7.49**：事实台账+证据引文不可篡改+伏笔三层提醒+量化AI味指标；修复期待线悬空检查崩溃
- **v7.48**：看板升级为十分区驾驶舱：写作热力/月度产出/质量矩阵/伏笔跨度，深色主题与 Ctrl+K 全局跳转
- **v7.47**：修复 8 项 P1 与 26 项 P2 缺陷（MCP Server 崩溃、只读契约失真、回忆标记双计、标题识别失效、快照 KeyError、修复管线空转、verify 隐藏写副作用、编码假绿等），统一跨脚本口径
- **v7.46**：发布包剔除无扩展名文件并补齐 SkillHub CLI 必需字段（slug/displayName/license），包内 doctor 自检与许可证声明对齐
- **v7.45**：章节索引与增量扫描、上下文预算控制器、测试分片
- **v7.44**：审校骨架生成器、语义弱证据降级、规则观察期到期机制、SKILL.md 瘦身至 50KB 以下
- **v7.43**：一键改版工具 bump_version.py、日期真源闸门、发布链 tag 与同号包门禁
- **v7.42**：交付 Gate 默认语义证据、墨尺自定义目录持久化、schemas 同步、发布包许可证与版本治理修复。
- **v7.41**：墨尺一键安装向导（clone+路径持久化+起服自检，免环境变量）、mochi_check 接入持久化兜底、台账 RB-031 观察态、dist 维护裁定。
- **v7.40**：前3章开篇闸门、ai-lite 百分制、对话三症状机械检测、平台参数表、期待线台账、主文件瘦身与版本历史外置。
- **v7.39**：安全写入授权、最小修复范围、Canonical Parser、30项语义证据 Gate、runtime 全量 parity 与回归补盲。
- **v7.38**：Apache 2.0 许可证、NOTICE、安全/贡献/仓库配置、CI 发布门和回归治理。
- **v7.37**：章节交付 Gate、全文修复编排、项目审计日志、轻量记忆检索、JSON Schema。
- **v7.36**：30 项核心校验注册表、规则 → 执行器 → 测试闭环。
- **v7.35**：全文审稿回归语义、修复队列状态层、规则台账和运行时版本治理。

---

## 社区交流

欢迎加入「冷漠网络小说科技交流群」交流写作经验、反馈问题与需求：

**QQ 群：1016190748**

---

## 项目地址

[GitHub / lenmo181/novel-writing-skill](https://github.com/lenmo181/novel-writing-skill)
