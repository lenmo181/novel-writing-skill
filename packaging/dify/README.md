# Dify 插件：网络小说创作校验（Web Novel Writing Validator）

把「网络小说创作技能」的机械硬卡校验包装成 Dify **工具插件**，
可在任意 Dify 工作流 / Agent 中调用，卡住不合格草稿。

---

## 为什么是「传文本」而不是「传文件路径」

Dify 插件跑在 **Dify 远端沙箱**里，**读不到用户本地磁盘**。
所以本插件的工具一律以 **正文文本** 为输入，在沙箱内落临时文件后跑校验脚本，
返回结果即销毁临时文件。这与 MCP Server（本地 stdio，可传路径）形成互补。

---

## 目录

```
packaging/dify/
├── manifest.yaml                      # 插件清单
├── main.py                            # 入口
├── requirements.txt                   # 仅 dify_plugin（运行时零第三方依赖）
├── icon.svg                           # 插件图标
├── PRIVACY.md                         # 隐私声明（上架必填）
├── helper.py                          # 共享工具：脚本定位 / 白名单 / 临时文件执行
├── provider/
│   ├── web_novel_writing.yaml
│   └── web_novel_writing.py
├── tools/
│   ├── check_chapter.yaml / .py       # 单章 13 项硬卡
│   └── list_validators.yaml / .py     # 列出内置校验器
├── bundle_skill.py                    # 把技能包复制进 _skill/
└── _skill/                            # ← 由 bundle_skill.py 生成（勿手工编辑）
```

---

## 工具

### `check_chapter`

对单章正文跑 13 项机械硬卡（字数带 / 格式 / 对话占比 / AI 味指数 / 文字墙 / 冲突值）。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `chapter_text` | ✅ | 本章全文 |
| `chapter_index` | | 章号；第 1–3 章额外启用黄金开篇闸门 |
| `platform` | | 平台预设（番茄 / 起点 / 知乎盐选），覆盖默认字数带与对话占比 |
| `quote` | | 引号口径（中文弯引号 / 半角双引号 / 不限） |

输出：文本报告 + JSON（`ok` / `exit_code` / `report`）。
**`exit_code != 0` 即存在硬伤，禁止交付**——可直接在工作流里做条件分支。

### `list_validators`

列出插件内置的 19 个只读校验器与解析到的脚本目录（用于排障）。

---

## 构建

### 1. 把技能包塞进插件

```bash
python packaging/dify/bundle_skill.py
```

### 2. 打包为 `.difypkg`

```bash
pip install dify-plugin-daemon        # 或用官方 CLI
dify plugin package packaging/dify -o dist/
```

产出 `dist/web_novel_writing.difypkg`。

### 3. 上架

- **私有部署**：`dify plugin install dist/web_novel_writing.difypkg`
- **上架 Marketplace**：登录 `https://marketplace.dify.ai` → 上传 `.difypkg` → 提交审核

> ⚠️ 上架审核需要 **有效的 `icon.svg` + `PRIVACY.md` + provider/tool YAML 描述完整**。
> 本目录三者均已就位。首次上架前请把 `manifest.yaml` 里的 `author`、`created_at`
> 换成你自己的署名与真实时间。

---

## 与 MCP Server 的分工

| | MCP Server | Dify 插件 |
| --- | --- | --- |
| 运行位置 | 用户本机（stdio） | Dify 沙箱 |
| 输入 | **文件路径**（可读本地项目） | **正文文本** |
| 适用 | 本地写作全流程、项目级体检 | 云端工作流/Agent 集成 |
| 分发 | PyPI + MCP Registry | `.difypkg` + Dify Marketplace |

两者共用同一套**只读白名单**与同一份技能脚本，行为一致。

---

## 验证

```bash
# 语法自检
python -m py_compile packaging/dify/main.py packaging/dify/helper.py \
  packaging/dify/provider/web_novel_writing.py \
  packaging/dify/tools/check_chapter.py \
  packaging/dify/tools/list_validators.py

# 确认技能已就位
python packaging/dify/bundle_skill.py
```
