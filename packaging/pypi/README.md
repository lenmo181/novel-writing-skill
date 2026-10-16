# PyPI 分发（`web-novel-writing-mcp`）

把技能包 + MCP Server 打成标准 wheel 发布到 PyPI，
使任意 MCP 宿主可一行 `uvx web-novel-writing-mcp` 启用，
同时满足 MCP Registry 对 `packages[].identifier` 的「真实可安装包」要求。

---

## 产物

| 文件 | 说明 |
| --- | --- |
| `dist/web_novel_writing_mcp-<ver>-py3-none-any.whl` | 可 `pip install` 的 wheel（约 600 KiB / 114 条目） |
| `packaging/pypi/build_pkg/` | 构建源树（可随时删除重建；`pyproject.toml` + `README.md` 为标准构建脚手架） |

**包内布局**

```
web_novel_writing_mcp/
├── __init__.py
├── __main__.py          # python -m web_novel_writing_mcp
├── server.py            # MCP Server（源真源 = packaging/mcp/server.py）
└── _skill/              # 完整技能包（105 文件）
    ├── SKILL.md
    ├── tools/           # config.py 的 parents[1] == _skill/ → doctor 全绿
    ├── references/
    ├── versions/
    └── ...
```

> 之所以把**整个技能包**打进 wheel，而不是只放几个脚本：
> `doctor.py` / `lint_skill.py` / `eval_skill.py` / `check_refs.py` 需要完整技能骨架才能通过；
> 只放脚本会让 `doctor` 直接报错，首次安装体验很差。

---

## 构建

```bash
python packaging/pypi/build_wheel.py
```

构建器是**纯标准库**（`zipfile` + `hashlib`），不依赖 `build` / `setuptools`，
与本技能「零第三方依赖」的工程约束一致。它依次完成：

1. 读 `SKILL.md` frontmatter 取版本（唯一真源）
2. 把技能包复制到 `build_pkg/web_novel_writing_mcp/_skill/`
3. 复制 `packaging/mcp/server.py` 进包
4. 生成 `dist-info`（METADATA / WHEEL / entry_points.txt / RECORD，哈希全部实算）
5. 打出 PEP 427 wheel
6. **自检**：`pip install --target` 到临时目录 → 跑 MCP 握手 → 调 `doctor` 工具 → 断言全绿

预期输出：

```
构建 web-novel-writing-mcp v7.46.0
  ✓ 打包技能文件 105 个
  ✓ wheel：dist\web_novel_writing_mcp-7.46.0-py3-none-any.whl  (615 KiB)
自检（安装到临时目录 + MCP 握手 + 跑 doctor）…
  ✓ 握手 OK：web-novel-writing v7.46.0
  ✓ doctor 输出：全绿
结论：通过 ✅
```

> 若环境已装 `setuptools>=62`，也可走标准构建：
> `cd packaging/pypi/build_pkg && python -m build --wheel`。

---

## 发布 SOP

### 1. 建 PyPI API Token

`https://pypi.org/manage/account/token/` → 新建 token，scope 选
「Entire account（首次）」或「Project: web-novel-writing-mcp（后续）」。
Token 形如 `pypi-AgEIcHlwaS5vcmc...`，**只显示一次**。

写入 `~/.pypirc`：

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...
```

### 2. 上传

```bash
python -m twine upload dist/web_novel_writing_mcp-7.46.0-py3-none-any.whl
```

无 `twine` 时先装：`pip install twine`（**仅发布机需要**，运行时不依赖任何第三方包）。

### 3. 验证

```bash
uvx web-novel-writing-mcp      # 应能启动并等待 stdin 上的 JSON-RPC
pip index versions web-novel-writing-mcp
```

### 4. 与 MCP Registry 联动

`packaging/mcp/server.json` 的 `packages[0].identifier` 必须是
**已真实上架**的 PyPI 包名与版本。PyPI 上传成功后，再走 MCP Registry 发布：

```bash
# 官方 publisher（需 GitHub OIDC 校验仓库归属 io.github.lenmo181/*）
mcp-publisher publish
```

---

## 发版清单（每次改版）

1. `python tools/bump_version.py --apply` —— 版本 + 日期同步全部登记点位
2. `python tools/doctor.py` —— 仓库态 91/91 全绿
3. 运行上架包构建脚本（`.workbuddy/` 下的 `build_market_zip.py`）—— 上架包（SkillHub）
4. `python packaging/pypi/build_wheel.py` —— wheel + 自检
5. 同步 `packaging/mcp/server.json` 的 `version` 与包版本
6. `twine upload` —— PyPI
7. `mcp-publisher publish` —— MCP Registry

---

## 已知边界

- **wheel 体积**：含全部中文手册与参考文档，约 600 KiB；这是刻意取舍（换取 `doctor` 可跑通）。
- **`assets/` 与 `packaging/` 不参与 `doctor` 目录树登记比对**：这两类目录已被上架包构建排除，
  若仍登记就会在包内变成「登记但不存在」的幽灵条目。v7.46 起 `doctor.py` 把豁免判据同时作用于
  登记侧与磁盘侧，仓库 / 上架包 / wheel 三态口径统一。
- **无 `Requires-Dist`**：纯标准库，`dependencies = []`。
