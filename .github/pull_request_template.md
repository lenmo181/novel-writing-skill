## 变更说明

- 变更目的：
- 影响范围：
- 是否涉及默认参数/规则口径：否
- 是否涉及正文写入逻辑：否
- 是否新增或修改测试：是/否

## 验证

- [ ] python tools/lint_skill.py
- [ ] python tools/check_refs.py
- [ ] python tools/eval_skill.py --json
- [ ] python -m unittest discover -s tests -p "test_*.py"

## 安全

- [ ] 未提交 API Key、密码、个人数据或未公开稿件
- [ ] 涉及正文写入时已说明备份/回滚方式
