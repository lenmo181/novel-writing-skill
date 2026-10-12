# -*- coding: utf-8 -*-
"""发版元数据一致性断言（v7.43）。

背景：v7.41 把 config.py 的 RELEASE_DATE 改成 2026-10-07，v7.42 又改成
2026-10-09，但两个测试里**复制**的日期没跟上，导致 CI 三门矩阵全红。
根因不是「忘了改」，而是「日期有真源却被复制进测试」——只要存在副本，
就一定会再次漂移。

因此本模块把断言从「值相等」改为：
    1. 格式与合理性（ISO 日期、不晚于今天）；
    2. 四真源互相印证（config.py == SKILL.md == README.md == CHANGELOG.md）。
这样改版只改真源，测试永远不需要跟着改；真源之间不一致时才会红。

用法：
    from release_meta import assert_release_consistent
    assert_release_consistent(self, ROOT, SKILL_VERSION, RELEASE_DATE)
"""

from datetime import date

VERSION_RE = r"^\d+\.\d+$"
_ISO_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


def _read(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def assert_release_consistent(tc, root, version, release_date):
    """校验版本/日期格式，并要求 config、SKILL.md、README.md、CHANGELOG.md 四源一致。"""
    tc.assertRegex(version, VERSION_RE, "版本号应为 主.次 两段数字")
    tc.assertRegex(release_date, _ISO_DATE_RE, "RELEASE_DATE 应为 YYYY-MM-DD")
    tc.assertLessEqual(date.fromisoformat(release_date), date.today(),
                       "RELEASE_DATE 不应是未来日期")

    skill = _read(root, "SKILL.md")
    readme = _read(root, "README.md")
    changelog = _read(root, "versions/CHANGELOG.md")

    tc.assertIn(
        f"v{version}（{release_date}）", skill,
        "SKILL.md 版本行与 config.py 不一致；改版请用 tools/bump_version.py，不要手改单点")
    tc.assertIn(
        f"v{version}**（{release_date}）", readme,
        "README.md 版本行与 config.py 不一致；改版请用 tools/bump_version.py")
    tc.assertIn(
        f"## v{version}（{release_date}）", changelog,
        "CHANGELOG.md 缺少当前版本条目或日期不一致（四段式：更新/修复/降级删除/验证证据）")
