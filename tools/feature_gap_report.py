#!/usr/bin/env python3
"""输出当前小说写作技能与参考项目的能力差距矩阵。

该脚本不依赖第三方库，适合在当前项目中作为“能力规划/接入路线”的
可执行检查入口。输出内容可以用于评审、版本规划和未来开发优先级排序。
"""
from __future__ import annotations

import argparse
import json
from typing import List, Dict, Any


CURRENT_SKILL = {
    "30项校验": "已具备",
    "长篇工程文件结构": "已具备",
    "自动全文审稿": "已具备",
    "修复编排和差异检查": "已具备",
    "上下文包与记忆检索": "已具备",
    "安全边界和只读白名单": "已具备",
    "MCP/Dify封装": "已具备",
    "作品可视化工作台": "弱项",
    "作者偏好记忆": "弱项",
    "新书初始化引导": "弱项",
    "模型/provider管理": "弱项",
    "导入导出与项目迁移": "弱项",
    "多用户/权限系统": "缺失",
    "前端产品入口": "缺失",
}

REFERENCE_PROJECTS = {
    "AI_NovelGenerator": {
        "结构化创作工作台": "已具备",
        "角色/派系关系图": "已具备",
        "分卷/arc/scene/chapter 管理": "已具备",
        "本地持久化与备份": "已具备",
        "AI 工作流节点编排": "已具备",
        "30项校验": "弱项",
        "全书工程式修复": "弱项",
        "长篇连续性治理": "弱项",
    },
    "chinese-novelist-skill": {
        "三层问答与初始化": "已具备",
        "偏好记忆": "已具备",
        "中断续写": "已具备",
        "多写作模式": "已具备",
        "自动校验修复": "已具备",
        "工程规则治理": "弱项",
        "项目级审校体系": "弱项",
        "安全边界": "弱项",
    },
    "MuMuAINovel": {
        "多模型接入": "已具备",
        "多用户与登录": "已具备",
        "项目管理": "已具备",
        "导入/导出": "已具备",
        "Docker/部署": "已具备",
        "长篇工程质量门禁": "弱项",
        "本地写作档案治理": "弱项",
        "审稿/修复闭环": "弱项",
    },
}

PRIORITY = [
    {
        "id": "P0-01",
        "feature": "作品管理与章节关系可视化",
        "value": "高",
        "feasibility": "高",
        "reason": "直接提高长篇维护效率并降低审校成本。",
    },
    {
        "id": "P0-02",
        "feature": "作者偏好记忆与初始化问答",
        "value": "高",
        "feasibility": "高",
        "reason": "降低首次使用门槛，并提升长期连续写作体验。",
    },
    {
        "id": "P0-03",
        "feature": "导入/导出与项目迁移",
        "value": "高",
        "feasibility": "高",
        "reason": "帮助作者接手旧稿和跨设备迁移，增强工程实用性。",
    },
    {
        "id": "P0-04",
        "feature": "模型/provider 管理层",
        "value": "中高",
        "feasibility": "中高",
        "reason": "减少单一服务商依赖，提高试错效率。",
    },
    {
        "id": "P1-01",
        "feature": "轻量 Web 管理端",
        "value": "中",
        "feasibility": "中",
        "reason": "提升产品体验但不影响当前工程能力。",
    },
    {
        "id": "P1-02",
        "feature": "多用户/权限协作",
        "value": "中",
        "feasibility": "中",
        "reason": "适合团队编辑和分工协作，但不是单人创作首要需求。",
    },
]


def matrix_payload() -> Dict[str, Any]:
    return {
        "current_skill": CURRENT_SKILL,
        "reference_projects": REFERENCE_PROJECTS,
        "priority": PRIORITY,
        "recommended_integration": [
            "project_state.py",
            "preference_memory.py",
            "project_export.py",
            "provider_config.py",
            "project_visualize.py",
        ],
    }


def render_text(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("==== 小说写作技能能力差距矩阵 ====")
    lines.append("")
    lines.append("[Current skill]")
    for k, v in payload["current_skill"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("[Reference projects]")
    for project, items in payload["reference_projects"].items():
        lines.append(f"- {project}:")
        for k, v in items.items():
            lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("[Priority]")
    for item in payload["priority"]:
        lines.append(
            f"- {item['id']} | {item['feature']} | value={item['value']} | feasibility={item['feasibility']} | reason={item['reason']}"
        )
    lines.append("")
    lines.append("[Recommended integration]")
    for name in payload["recommended_integration"]:
        lines.append(f"- {name}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="输出当前项目与参考项目的能力差距矩阵")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    payload = matrix_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
