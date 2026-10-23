"""CIReport: the result of the checks. Public schema, version 1 (schemas/ci-report.schema.json).

Stable on purpose: no time, findings and checks in a fixed order — the same project gives
the same bytes, so the report can live in git and be compared by snapshot tests.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reqgraph.checks.base import GROUP_TITLES, Finding, Group

Status = Literal["passed", "warning", "failed", "skipped"]
_STATUS_TEXT = {
    "passed": "пройдено",
    "warning": "предупреждения",
    "failed": "ошибки",
    "skipped": "пропущено",
}
_SEVERITY_TEXT = {"error": "ошибка", "warning": "предупреждение", "info": "к сведению"}
_OWNER_TEXT = {"analyst": "Analyst", "modeler": "Modeler", "standards": "Standards"}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CheckResult(_Model):
    id: str
    title: str
    group: Group
    status: Status
    errors: int = 0
    warnings: int = 0
    infos: int = 0


class Summary(_Model):
    errors: int  # findings by severity
    warnings: int
    infos: int
    passed: int  # checks by status
    warned: int
    failed: int
    skipped: int


def plural(n: int, one: str, few: str, many: str) -> str:
    """`plural(3, "ошибка", "ошибки", "ошибок")` -> «3 ошибки»."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


class CIReport(_Model):
    schema_version: Literal[1] = 1
    project: str
    checks: list[CheckResult]
    findings: list[Finding]
    summary: Summary

    @property
    def ok(self) -> bool:
        """No errors: warnings and notes do not stop the pipeline."""
        return self.summary.errors == 0

    def to_json(self) -> str:
        data = self.model_dump(mode="json")
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    def headline(self) -> str:
        s = self.summary
        found = ", ".join(
            [
                plural(s.errors, "ошибка", "ошибки", "ошибок"),
                plural(s.warnings, "предупреждение", "предупреждения", "предупреждений"),
            ]
        )
        checks = (
            f"проверок: пройдено {s.passed}, с ошибками {s.failed}, "
            f"с предупреждениями {s.warned}, пропущено {s.skipped}"
        )
        return f"{found} — {checks}"

    def to_markdown(self) -> str:
        lines = [f"# Отчёт проверок: {self.project}", ""]
        if not self.checks:
            return "\n".join([*lines, "Проверок не запускалось.", ""])
        lines += [f"**Итог:** {self.headline()}", ""]
        lines += [
            "| Группа | Проверка | Статус | Ошибки | Предупреждения |",
            "|---|---|---|---|---|",
        ]
        for c in self.checks:
            lines.append(
                f"| {GROUP_TITLES[c.group]} | {c.id} · {c.title} | {_STATUS_TEXT[c.status]} "
                f"| {c.errors} | {c.warnings} |"
            )
        titles = {c.id: c.title for c in self.checks}
        current = None
        for f in self.findings:
            if f.check_id != current:
                current = f.check_id
                lines += ["", f"## {f.check_id} · {titles.get(f.check_id, '')}", ""]
            where = f" · {', '.join(f.node_ids)}" if f.node_ids else ""
            line = f"- **{_SEVERITY_TEXT[f.severity]}**{where} — {f.message}"
            if f.hint:
                line += f" — *как исправить:* {f.hint}"
            lines.append(f"{line} ({_OWNER_TEXT[f.owner]})")
        return "\n".join(lines) + "\n"
