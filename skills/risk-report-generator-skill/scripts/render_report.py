# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def render(report: dict[str, Any]) -> str:
    lines = [
        f"# 供应链风险调查报告",
        "",
        f"- 报告编号：{report.get('reportId', '')}",
        f"- 总体风险：{report.get('overallRiskLevel', '')}",
        f"- 调查对象：{report.get('question', '')}",
        "",
        "## 结论摘要",
        "",
        str(report.get("summary") or ""),
        "",
        "## 分项发现",
        "",
    ]
    for finding in report.get("findings") or []:
        lines.append(f"### {finding.get('riskType')}（{finding.get('riskLevel')}）")
        lines.append("")
        lines.append(f"- 对象：{json.dumps(finding.get('subject') or {}, ensure_ascii=False)}")
        facts = finding.get("facts") or []
        if isinstance(facts, list):
            for fact in facts:
                lines.append(f"- 事实：{fact}")
        else:
            lines.append(f"- 事实：{facts}")
        lines.append(f"- 根因：{finding.get('rootCause', '')}")
        lines.append(f"- 消解：{finding.get('mitigation', '')}")
        lines.append(f"- 建议：{finding.get('recommendation', '')}")
        lines.append("")
    lines += ["## 待确认问题", ""]
    questions = report.get("openQuestions") or []
    if not questions:
        lines.append("- 无")
    else:
        for q in questions:
            lines.append(f"- {q}")
    lines += ["", "## 证据索引", ""]
    for ref in report.get("evidenceRefs") or []:
        lines.append(f"- {json.dumps(ref, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    src = Path(sys.argv[1])
    report = json.loads(src.read_text(encoding="utf-8"))
    md = render(report)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".md")
    out.write_text(md, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
