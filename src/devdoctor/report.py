from __future__ import annotations

import json
from typing import Any, Dict

from .models import Report, Status

SCHEMA_VERSION = 1
_MARK = {Status.OK: "[ OK ]", Status.WARN: "[WARN]", Status.FAIL: "[FAIL]"}


def to_dict(report: Report) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "devdoctor",
        "tool_version": report.tool_version,
        "platform": dict(report.platform),
        "overall": report.overall.label,
        "exit_code": report.exit_code,
        "summary": report.summary(),
        "checks": [c.to_dict() for c in report.checks],
    }


def to_json(report: Report) -> str:
    # sort_keys + fixed indent + no timestamps => byte-identical output for identical state
    return json.dumps(to_dict(report), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def to_text(report: Report) -> str:
    p = report.platform
    lines = [
        f"devdoctor {report.tool_version} - developer environment report",
        f"platform: {p.get('system', '?')} {p.get('machine', '?')}, {p.get('python_implementation', '?')}",
        "-" * 60,
    ]
    for c in report.checks:
        lines.append(f"{_MARK[c.status]} {c.title}: {c.message}")
    s = report.summary()
    lines += ["-" * 60,
              f"result: {report.overall.label.upper()}  "
              f"({s['ok']} ok, {s['warn']} warn, {s['fail']} fail)  exit code {report.exit_code}"]
    return "\n".join(lines) + "\n"
