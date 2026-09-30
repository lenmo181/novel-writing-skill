# 贡献指南

感谢参与网络小说创作技能。

## 开始前

请先阅读 README.md、SECURITY.md 和相关手册。提交前请确保没有包含 API Key、密码、个人隐私、未公开小说正文或其他不应公开的数据。

## 开发原则

- 新功能优先使用 Python 标准库，除非明确记录依赖理由。
- 默认诊断工具应保持只读；涉及正文、档案或大纲写入时，必须提供明确的备份/快照与失败回滚路径。
- 新增规则必须进入《规则台账》，并绑定执行器、测试入口和证据等级。
- 修改默认参数必须同步 tools/config.py、相关手册与回归测试。
- 不以制造文本指标的方式“过检”；警告项不得未经证据升级为硬卡。

## 本地验证

```bash
python tools/lint_skill.py
python tools/check_refs.py
python tools/eval_skill.py --json
python tools/doctor.py --runtime-smoke --package-smoke
python -m unittest discover -s tests -p "test_*.py"
```

## Pull Request

PR 描述请说明变更目的、影响范围、权限/写入边界以及验证结果。涉及规则、默认值、许可证或外部服务时，请明确写出兼容性影响。

## 许可证

提交到仓库并被接受的贡献，除非另有明确书面约定，按仓库 LICENSE 中的 Apache License 2.0 条款处理。第三方代码/内容仍按原许可证执行。
