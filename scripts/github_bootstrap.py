"""Create labels, milestones and issues for reqgraph in GitHub via REST (`gh api`).

Reads tasks from docs/backlog.md. Idempotent: labels and milestones are matched by name,
issues by the "T-xxx:" title prefix; existing objects are left alone unless --update is given.
GraphQL is not used (it is blocked in cloud sessions).

Usage:
    python scripts/github_bootstrap.py --dry-run
    python scripts/github_bootstrap.py
    python scripts/github_bootstrap.py --update      # also sync existing objects with this script
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "backlog.md"
DEFAULT_REPO = "Axx-Axvd/reqgraph"
BLOB = "https://github.com/{repo}/blob/main/"

LABELS: dict[str, tuple[str, str]] = {
    "epic:E0": ("0e8a16", "E0 · Фундамент"),
    "epic:E1": ("1d76db", "E1 · Граф, DSL, проверки"),
    "epic:E2": ("5319e7", "E2 · Агенты"),
    "epic:E3": ("b60205", "E3 · Интервью и данные"),
    "epic:E4": ("d93f0b", "E4 · Экспорт и evals"),
    "epic:E5": ("fbca04", "E5 · Веб и деплой"),
    "epic:E6": ("006b75", "E6 · Эксперименты"),
    "epic:E7": ("0052cc", "E7 · Релиз"),
    "type:feature": ("a2eeef", "Новая функциональность"),
    "type:bug": ("d73a4a", "Ошибка"),
    "type:docs": ("0075ca", "Документация"),
    "type:research": ("d4c5f9", "Исследование, эксперимент, разметка"),
    "type:infra": ("c5def5", "Репозиторий, CI, база, деплой"),
    "area:core": ("bfdadc", "graph/, store, llm/, cli"),
    "area:agents": ("bfdadc", "agents/, prompts/"),
    "area:checks": ("bfdadc", "checks/"),
    "area:dsl": ("bfdadc", "dsl/"),
    "area:exporters": ("bfdadc", "exporters/"),
    "area:api": ("bfdadc", "apps/api"),
    "area:web": ("bfdadc", "apps/web"),
    "area:evals": ("bfdadc", "evals/, sim/"),
    "area:infra": ("bfdadc", ".github/, supabase/, docker"),
    "needs:you": ("e99695", "Нужно решение или участие автора"),
    "blocked": ("000000", "Заблокировано зависимостью или внешним фактором"),
}

# Milestone due dates: end of day in Moscow (UTC+3) expressed in UTC.
MILESTONES: dict[str, str] = {
    "M0": "2026-11-01",
    "M1": "2026-11-15",
    "M2": "2026-11-29",
    "M3": "2026-12-13",
    "M4": "2026-12-27",
    "M5": "2027-01-24",
    "M6": "2027-02-07",
    "M7": "2027-02-21",
}

# T-xxx -> (type, area or None). Area labels follow the package layout in 02_arch.md.
CLASSIFY: dict[str, tuple[str, str | None]] = {
    "T-001": ("infra", "infra"),
    "T-002": ("docs", "infra"),
    "T-003": ("infra", "infra"),
    "T-004": ("infra", "infra"),
    "T-005": ("feature", "core"),
    "T-006": ("research", "evals"),
    "T-101": ("feature", "core"),
    "T-102": ("feature", "core"),
    "T-103": ("feature", "dsl"),
    "T-104": ("feature", "dsl"),
    "T-105": ("feature", "checks"),
    "T-106": ("feature", "checks"),
    "T-107": ("feature", "checks"),
    "T-201": ("feature", "agents"),
    "T-202": ("feature", "agents"),
    "T-203": ("feature", "agents"),
    "T-204": ("feature", "agents"),
    "T-205": ("feature", "agents"),
    "T-206": ("feature", "agents"),
    "T-301": ("feature", "agents"),
    "T-302": ("feature", "evals"),
    "T-303": ("research", "evals"),
    "T-304": ("feature", "evals"),
    "T-401": ("feature", "exporters"),
    "T-402": ("feature", "exporters"),
    "T-403": ("feature", "exporters"),
    "T-404": ("feature", "checks"),
    "T-405": ("feature", "evals"),
    "T-406": ("infra", "evals"),
    "T-501": ("feature", "api"),
    "T-502": ("feature", "api"),
    "T-503": ("feature", "api"),
    "T-504": ("feature", "web"),
    "T-505": ("feature", "web"),
    "T-506": ("infra", "infra"),
    "T-507": ("infra", "infra"),
    "T-601": ("research", "evals"),
    "T-602": ("research", "evals"),
    "T-603": ("research", "evals"),
    "T-604": ("research", "evals"),
    "T-605": ("research", "evals"),
    "T-701": ("feature", "web"),
    "T-702": ("docs", None),
    "T-703": ("docs", None),
}

EPIC_DOCS: dict[str, list[str]] = {
    "E0": ["docs/tech-design/02_arch.md", "docs/tech-design/10_claude.md"],
    "E1": ["docs/tech-design/04_data.md", "docs/tech-design/05_ci.md"],
    "E2": ["docs/tech-design/03_agents.md", "docs/tech-design/05_ci.md"],
    "E3": ["docs/tech-design/03_agents.md", "docs/tech-design/09_eval.md"],
    "E4": ["docs/tech-design/05_ci.md", "docs/tech-design/09_eval.md"],
    "E5": ["docs/tech-design/07_deploy.md", "docs/tech-design/04_data.md"],
    "E6": ["docs/tech-design/09_eval.md", "docs/tech-design/06_models.md"],
    "E7": ["docs/tech-design/09_eval.md", "docs/tech-design/08_plan.md"],
}
TASK_DOCS: dict[str, list[str]] = {
    "T-002": ["docs/adr/README.md"],
    "T-003": ["docs/tech-design/07_deploy.md"],
    "T-004": ["docs/tech-design/04_data.md", "docs/tech-design/07_deploy.md", "docs/adr/007-supabase.md"],
    "T-005": ["docs/tech-design/06_models.md", "docs/adr/003-llm-router.md"],
    "T-006": ["docs/tech-design/06_models.md", "docs/adr/011-models.md"],
    "T-101": ["docs/adr/004-artifact-graph.md"],
    "T-102": ["examples/garage61/REVIEW.md"],
    "T-103": ["docs/adr/005-process-dsl.md"],
    "T-104": ["docs/adr/010-diagrams.md"],
    "T-105": ["docs/adr/006-deterministic-checks.md"],
    "T-107": ["examples/garage61/REVIEW.md"],
    "T-502": ["docs/adr/009-pg-queue.md", "docs/adr/002-langgraph.md"],
    "T-506": ["docs/adr/008-deploy.md"],
}

MARKER = "<!-- reqgraph-bootstrap:{tid} -->"


@dataclass
class Task:
    tid: str
    title: str
    epic: str
    sprint: str
    acceptance: str
    depends: list[str]
    status: str | None
    needs_you: bool
    labels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- backlog parsing


def parse_backlog(text: str) -> tuple[list[Task], dict[str, str]]:
    """Return tasks and sprint goals (M0..M7 -> goal) from docs/backlog.md."""
    sprint_of: dict[str, str] = {}
    goals: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*S(\d)\s*·[^|]*\|[^|]*\|\s*M(\d)\s*\|([^|]*)\|([^|]*)\|", line)
        if m:
            goals[f"M{m.group(2)}"] = m.group(3).strip()
            for tid in re.findall(r"T-\d{3}", m.group(4)):
                sprint_of[tid] = f"M{m.group(1)}"

    tasks: list[Task] = []
    epic = ""
    current: dict[str, Any] | None = None

    def flush() -> None:
        if current is None:
            return
        tid = current["tid"]
        acc = current.get("acc", "")
        tasks.append(
            Task(
                tid=tid,
                title=current["title"],
                epic=epic_of[tid],
                sprint=sprint_of[tid],
                acceptance=acc.replace("**[you]**", "[you]"),
                depends=re.findall(r"T-\d{3}", current.get("dep", "")),
                status=current.get("status"),
                needs_you="[you]" in acc,
            )
        )

    epic_of: dict[str, str] = {}
    for line in text.splitlines():
        if m := re.match(r"## (E\d) ·", line):
            flush()
            current = None
            epic = m.group(1)
        elif m := re.match(r"### (T-\d{3}) — (.+)", line):
            flush()
            current = {"tid": m.group(1), "title": m.group(2).strip()}
            epic_of[m.group(1)] = epic
        elif line.startswith("## "):
            flush()
            current = None
        elif current is not None and (m := re.match(r"- \*\*(.+?):\*\*\s*(.*)", line)):
            key = {"Критерий приёмки": "acc", "Зависит от": "dep", "Статус": "status"}.get(m.group(1))
            if key:
                current[key] = m.group(2).strip()
    flush()

    for t in tasks:
        kind, area = CLASSIFY[t.tid]
        t.labels = [f"epic:{t.epic}", f"type:{kind}"]
        if area:
            t.labels.append(f"area:{area}")
        if t.needs_you:
            t.labels.append("needs:you")
    return tasks, goals


def render_body(t: Task, repo: str, numbers: dict[str, int]) -> str:
    blob = BLOB.format(repo=repo)
    deps = ", ".join(f"#{numbers[d]} ({d})" if d in numbers else d for d in t.depends) if t.depends else "—"
    docs = ["docs/backlog.md", *EPIC_DOCS[t.epic], *TASK_DOCS.get(t.tid, [])]
    lines = [
        MARKER.format(tid=t.tid),
        f"**{t.tid}** · эпик {t.epic} · веха {t.sprint}",
        "",
        "## Описание",
        "",
        f"{t.title}.",
        "",
        "## Критерии приёмки",
        "",
        f"- [ ] {t.acceptance}",
        "- [ ] pytest, ruff, mypy зелёные; DoD отмечен в docs/backlog.md; запись в docs/journal.md",
        "",
        f"**Зависит от:** {deps}",
        "",
    ]
    if t.status:
        lines += [f"> **Частично сделано:** {t.status}", ""]
    lines += ["## Ссылки", ""]
    lines += [f"- [{d}]({blob}{d})" for d in dict.fromkeys(docs)]
    lines += ["", "Порядок работы: [docs/prompts/task.md](" + blob + "docs/prompts/task.md)"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- GitHub REST via gh


class GitHub:
    def __init__(self, repo: str, dry_run: bool) -> None:
        self.repo = repo
        self.dry_run = dry_run

    def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        cmd = ["gh", "api", "--method", method, f"repos/{self.repo}/{path}"]
        if payload is not None:
            cmd += ["--input", "-"]
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"gh api {method} {path} failed: {proc.stderr.strip() or proc.stdout}")
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def list_all(self, path: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        sep = "&" if "?" in path else "?"
        while True:
            chunk = self.call("GET", f"{path}{sep}per_page=100&page={page}")
            out += chunk
            if len(chunk) < 100:
                return out
            page += 1

    def write(self, method: str, path: str, payload: dict[str, Any]) -> Any:
        if self.dry_run:
            return None
        return self.call(method, path, payload)


# ---------------------------------------------------------------- sync steps


def sync_labels(gh: GitHub, update: bool) -> None:
    existing = {lb["name"]: lb for lb in gh.list_all("labels")}
    for name, (color, desc) in LABELS.items():
        cur = existing.get(name)
        if cur is None:
            print(f"  + label   {name:<16} #{color}  {desc}")
            gh.write("POST", "labels", {"name": name, "color": color, "description": desc})
        elif update and (cur["color"] != color or (cur.get("description") or "") != desc):
            print(f"  ~ label   {name:<16} -> #{color}  {desc}")
            gh.write("PATCH", f"labels/{name.replace(':', '%3A')}", {"color": color, "description": desc})
        else:
            print(f"  = label   {name}")


def sync_milestones(gh: GitHub, goals: dict[str, str], update: bool) -> dict[str, int]:
    existing = {ms["title"]: ms for ms in gh.list_all("milestones?state=all")}
    numbers: dict[str, int] = {}
    for title, day in MILESTONES.items():
        due = f"{day}T20:59:59Z"
        payload = {"title": title, "due_on": due, "description": goals.get(title, "")}
        cur = existing.get(title)
        if cur is None:
            print(f"  + milestone {title}  due {day} (23:59 МСК)  {payload['description']}")
            res = gh.write("POST", "milestones", payload)
            numbers[title] = res["number"] if res else -1
        else:
            numbers[title] = cur["number"]
            changed = cur.get("due_on") != due or (cur.get("description") or "") != payload["description"]
            if update and changed:
                print(f"  ~ milestone {title}  due {day}")
                gh.write("PATCH", f"milestones/{cur['number']}", payload)
            else:
                print(f"  = milestone {title} (#{cur['number']})")
    return numbers


def sync_issues(gh: GitHub, tasks: list[Task], ms: dict[str, int], update: bool) -> None:
    existing: dict[str, dict[str, Any]] = {}
    for it in gh.list_all("issues?state=all"):
        if "pull_request" in it:
            continue
        if m := re.match(r"(T-\d{3}):", it["title"]):
            existing.setdefault(m.group(1), it)
    numbers = {tid: it["number"] for tid, it in existing.items()}

    created: list[Task] = []
    for t in tasks:
        title = f"{t.tid}: {t.title}"
        payload = {
            "title": title,
            "body": render_body(t, gh.repo, numbers),
            "labels": t.labels,
            "milestone": ms[t.sprint],
        }
        cur = existing.get(t.tid)
        if cur is None:
            deps = ",".join(t.depends) or "—"
            print(f"  + issue {title}")
            print(f"        {t.sprint} | {', '.join(t.labels)} | deps: {deps}" + (" | частично" if t.status else ""))
            res = gh.write("POST", "issues", payload)
            if res:
                numbers[t.tid] = res["number"]
                created.append(t)
        elif update:
            print(f"  ~ issue #{cur['number']} {title}")
            created.append(t)
        else:
            print(f"  = issue #{cur['number']} {title}")

    # second pass: dependency links need the final issue numbers
    for t in created:
        if t.depends:
            body = render_body(t, gh.repo, numbers)
            payload: dict[str, Any] = {"body": body}
            if update:
                payload |= {"title": f"{t.tid}: {t.title}", "labels": t.labels, "milestone": ms[t.sprint]}
            gh.write("PATCH", f"issues/{numbers[t.tid]}", payload)
        elif update and t.tid in existing:
            gh.write(
                "PATCH",
                f"issues/{numbers[t.tid]}",
                {
                    "title": f"{t.tid}: {t.title}",
                    "body": render_body(t, gh.repo, numbers),
                    "labels": t.labels,
                    "milestone": ms[t.sprint],
                },
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    ap.add_argument("--update", action="store_true", help="overwrite existing labels, milestones, issues")
    ap.add_argument("--show-body", metavar="T-xxx", help="print the rendered issue body and exit")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tasks, goals = parse_backlog(BACKLOG.read_text(encoding="utf-8"))
    missing = [t.tid for t in tasks if t.tid not in CLASSIFY]
    if missing:
        print(f"no type/area mapping for: {missing}", file=sys.stderr)
        return 2
    if args.show_body:
        print(render_body(next(t for t in tasks if t.tid == args.show_body), args.repo, {}))
        return 0

    gh = GitHub(args.repo, args.dry_run)
    mode = "DRY RUN — nothing is written" if args.dry_run else "APPLY"
    print(f"{mode}: {args.repo}, {len(LABELS)} labels, {len(MILESTONES)} milestones, {len(tasks)} issues")
    print("labels:")
    sync_labels(gh, args.update)
    print("milestones:")
    ms = sync_milestones(gh, goals, args.update)
    print("issues:")
    sync_issues(gh, tasks, ms, args.update)
    return 0


if __name__ == "__main__":
    sys.exit(main())
