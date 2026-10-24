# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `reqgraph init` and `reqgraph run` (T-206): `agents/run.py` — `init_project()` writes `reqgraph.yaml` and
  `brief.md`; `run_project()` runs brief → Analyst → Modeler → Standards → checks → repair on a project folder,
  prints a line per step, writes the project, `reports/ci-report.json|md`, `run-events.jsonl` and
  `run-summary.json` (models, prompt hashes, temperature, seeds, tokens, $, time); exit code 0 / 1 (errors left) /
  2 (cannot run); a reference project is refused. End-to-end test of `reqgraph run` on the dev-01 brief from a
  cassette. `scripts/terminal_svg.py` (saved terminal output → SVG with rich), `docs/demo/m2.md` and the README
  demo; the three dev runs of 24.10 are kept in `evals/runs/2026-10-24/`. `reqgraph-evals repair` also records the
  checks left with errors, SCH-* errors and processes without SND-* errors after repair.
- Reviewer and the repair loop (T-205): `agents/reviewer.py` — errors grouped by owner and node (at most 10 tasks),
  TPL-001 on a section listed from the graph goes to the owner of those nodes with an explanation of what is missing,
  the LLM words the instruction of each group (`ReviewerDraft`, a skipped group keeps the template text),
  `RunContext.reviewer="template"` for the «without Reviewer» ablation; repeat detector — the same error fingerprints
  in three reports in a row stop the run with `needs_human`; `RunState.history`; a stopped run goes straight to
  export. `reqgraph-evals repair [--reviewer template]`.

### Fixed

- Analyst: an edit of an existing requirement no longer wipes fields the model did not send (acceptance criteria).
- guard(): links to a document section added in the same patch were dropped.
- Standards agent and TPL-001 (T-204): own SRS structure `standards/iso29148_srs.yaml` (section names only, ADR-012;
  `fill` says where the content comes from, `required` feeds TPL-001); `agents/standards.py` builds sections from the
  graph by code (actors, BR, UR, FR, NFR, CON, entities, processes, acceptance criteria, assumptions) with
  `rendered_in` links, the LLM writes purpose, scope and glossary (`StandardsDraft`, one retry when a field is empty);
  `checks/template.py` — TPL-001 (moved here from T-404: the T-204 threshold is measured with it), skipped until
  sections exist. `reqgraph-evals standards`.
- Modeler agent (T-203): `agents/modeler.py` — the model fills `ModelerDraft` (processes almost in the DSL, entities
  as tables), `to_models()` builds the patch and the ERD text (process and entity ids predicted with the allocator
  `apply()` uses, DBML written by code with `Note: 'ENT-xx · Название'`, realized_by from `realizes`); the Modeler
  checks its own models (SCH-001…003, SND-001, SND-003, SND-004, TRC-002) and answers again with the problems, at
  most 3 answers. `dsl.dbml.render_dbml()`; `RunState.files` keeps model texts written during a run; `guard()`
  accepts links to the ids the patch's adds will get. `reqgraph-evals modeler`. `llm/roles.yaml` (free): `modeler`
  uses the long-context ladder of `analyst`.
- Analyst agent (T-202): `agents/analyst.py` — the model fills a flat `AnalystDraft` (actors, requirements,
  removals), `to_patch()` builds the GraphPatch (ids and links by code, new nodes validated first, existing ones
  updated only where changed); `agents/guard.py` — `guard()` drops other agents' node kinds, approved nodes,
  unknown ids and forbidden links with a reason; one retry with the reasons; prompts in
  `agents/prompts/analyst/*.md` (Jinja2, prompt hash in `llm_call` events); brief paragraphs become client turns.
  `reqgraph-evals analyst` runs the Analyst on the dev briefs `evals/scenarios/dev-01…03` (drafts) and writes
  `evals/reports/analyst-*.csv|md`. New dependency of `packages/core`: `jinja2==3.1.6` (BSD-3-Clause, already in the
  lock through evals).
- Agent run graph on LangGraph (T-201): `agents/state.py` (`RunState`, `Coverage`, `RepairTask`, `BudgetState`),
  `agents/runtime.py` (`RunContext` as LangGraph context: project, store, stub models, events in memory or JSONL,
  limits and profile from `reqgraph.yaml`; checkpoint serializer with an allow list of our types),
  `agents/nodes.py` and `agents/graph.py` (10 nodes of 03_agents, modes interview / brief / check, `interrupt()` for
  answers, repair loop up to `checks.max_iterations`, budget stop with a report). Agents are stubs around one
  `structured()` call; the Reviewer builds repair tasks from the report by template. Agents refuse to run on a
  reference project. `llm.router.structured(model=...)` takes a ready model (stub models in tests). New dependency
  of `packages/core`: `langgraph==1.2.16` (MIT, loaded only with `reqgraph.agents`).
- Checks ISO-001…005 and TRC-001…006 (T-107): vague words (own dictionary `checks/vague_words.yaml`, Russian by
  pymorphy3 lemmas), one statement per FR, verifiability, placeholders, EARS form; BR refined, FR realized, no orphan
  model elements, references to steps and attributes, refines / depends_on cycles, DSL `realizes` mirrors
  `realized_by`, entities named in FRs (Russian entity name from the DBML note `ENT-05 · Запись`, otherwise skipped),
  sources are client turns. garage61: Russian entity names added (author's decision), all 20 checks pass.
  All 10 mutations of garage61/REVIEW.md are covered. New dependencies of `packages/core`: `pymorphy3==2.0.6`
  (MIT, created lazily), `rapidfuzz==3.14.6` (MIT).
- Checks SCH-001…005 and SND-001…004 (T-106): BPMN against the XSD, process DSL and its references, DBML, PlantUML
  and Structurizr through Kroki (skipped offline), reachability (networkx), soundness through pm4py with the DSL
  adapter `dsl/soundness.py` (ADR-014, lazy import), gateways, one process per page. Fixtures: garage61 is clean,
  bad cases are mutations of it (`tests/checks/fixtures/bad/mutations.yaml`). New dependency of `packages/core`:
  `pm4py==2.7.23.11` (AGPL-3.0-or-later, accepted in ADR-014; imported only by SND-002).
- Checks framework (T-105): `reqgraph.checks` — `Finding` (with a fingerprint for the repeat detector), `BaseCheck`,
  `CheckContext` (parsed processes and ERD, SVG through Kroki), `@register`, `run_checks()` (async; disabled and
  skipped checks, a crashing check becomes an error finding); **public schema, version 1:**
  `schemas/ci-report.schema.json` — stable JSON and Russian Markdown; CLI `reqgraph check` (exit codes 0/1/2,
  `reports/ci-report.{json,md}`).
- Models as code (T-104): `reqgraph.dsl.dbml` (pydbml: tables, columns, relations, enums; entities `ENT-xx`),
  `dsl.plantuml` / `dsl.c4` readers, `dsl.readers.model_readers()` for `FileStore(root, readers=...)`;
  `dsl.kroki.render_svg()` — SVG of DBML, PlantUML, Structurizr and BPMN through Kroki (`KROKI_URL`), compile
  errors with the line, `offline` without network, disk cache (`REQGRAPH_CACHE_DIR`); CLI `reqgraph render`.
  New dependency of `packages/core`: `pydbml==1.2.1` (MIT).
- One process = one page (author's rule): narrow columns for events and gateways, `dsl.layout.page_font_pt()`
  (A4 landscape, minimum 6 pt); new planned check SND-004 (warning) — 22 checks.
- Process DSL and BPMN compiler (T-103): `reqgraph.dsl.process.ProcessDSL` (**public schema, version 1:**
  `schemas/process-dsl.schema.json`), `compile_bpmn()` to BPMN 2.0 XML with lanes and diagram layout
  (`dsl/layout.py`, networkx), element ids equal graph references (`PRC-01.T05`), `validate_bpmn()` against the
  official OMG XSD bundled in `dsl/xsd/` (from camunda-bpmn-model 7.24.0, Apache-2.0); golden BPMN tests;
  CLI `reqgraph bpmn`. New dependencies of `packages/core`: `lxml==6.1.3`, `networkx==3.7` (BSD).
- Project store (T-102): `reqgraph.graph.store.FileStore` reads a project folder into `Project` (config, graph,
  texts) and writes it back; unchanged files are written byte for byte, changed ones in a canonical form;
  `trace/edges.yaml` is regenerated, `trace/ids.yaml` keeps id high-water marks; interim scanner of DBML,
  PlantUML and Structurizr files for ENT/UC/C4 ids (replaced in T-104). `ArtifactGraph.from_parts()`.
  **Public schema, version 1:** `schemas/project-config.schema.json` (format of `reqgraph.yaml`).
- Artifact graph (T-101): `reqgraph.graph` with 12 node kinds, 6 relations and the table of allowed kind pairs,
  `GraphPatch` (ops `add`, `link`, `unlink`, `update`, `remove`), `ArtifactGraph.apply()` (all or nothing, returns
  `ApplyResult` with the id map and a diff), `IdAllocator` (ids issued by code, never reused), lock on `approved`
  nodes for `actor="agent"`, stable JSON. **Public schemas, version 1:** `schemas/graph-patch.schema.json` and
  `schemas/artifact-graph.schema.json`, generated by `uv run reqgraph schemas` and checked by a test.
  `pydantic` is now a direct dependency of `packages/core` (was transitive via pydantic-ai).
- ADR-017: agents on one model with reserves; the stakeholder simulator and the judge are another family
  (enforced by a test). Free profile built by probe and a long-interview check; Qwen on Groq for simulator and judge.
- Model probe (T-006): workspace member `evals/` (`reqgraph-evals probe | rescore`) on pydantic-evals, 20 tasks in
  4 blocks, deterministic scores, CSV with reproducibility fields and stored answers; first report 2026-10-23.
- `structured(..., model_id=...)` pins one model without fallback.
- LLM layer (T-005): `reqgraph.llm.structured()` on pydantic-ai with `roles.yaml` (profiles free / cheap / local),
  fallback ladder, per-provider context limit and seed support, run budget, actual and list cost; cassettes for
  OpenRouter, Groq and Gemini. Session rule `docs/prompts/plans.md` (plans with a plain-language part).
- Supabase schema (T-004): migrations `init` (profiles with auth trigger, projects, graph_revisions, runs, run_events,
  interview_turns, exports, usage_daily) and `rls` (RLS on all public tables, Realtime for run_events and
  interview_turns), local seed, pgTAP RLS tests, CI job `db`; Supabase CLI 2.121.0 as a root devDependency.
- ADR template (`docs/adr/template.md`) and CI badge in README (T-002).
- GitHub Actions `ci.yml` (T-003): ruff, mypy, pytest with coverage report, pre-commit, web lint and build on ubuntu and windows;
  aggregate check `ci` for branch protection.
- Monorepo skeleton (T-001): uv workspace with `packages/core` (`reqgraph` package, layer packages,
  `reqgraph --version` from package metadata) and `apps/api` (stub until T-501); pnpm workspace with
  `apps/web` (Next.js 16.4.2, TypeScript strict, ESLint); ruff, mypy strict, pytest with
  `--disable-socket`, pytest-cov (report only) and pre-commit.
- Technical design, ADR 001–012, backlog and the garage61 reference project (draft).
- Preflight (stage 0): session prompts in `docs/prompts/`, development journal, GitHub templates,
  Dependabot, `.gitattributes`, `.editorconfig`, `scripts/doctor.py`, `scripts/github_bootstrap.py`,
  setup guides in `docs/setup/` and version research in `docs/research/`.
- ADR-013 (LLM layer on pydantic-ai), ADR-014 (soundness via pm4py with a DSL adapter),
  ADR-016 (DOCX export via pandoc); ADR-015 (Streamlit demo) recorded as rejected.

### Changed

- 06_models, 07_deploy, 09_eval: current free models, DeepSeek V4 Pro price (0.955 / 1.911 on 2026-10-23), payment from
  Russia through ruble aggregators, risk R7. CLAUDE.md: network-blocking flag, mypy command.
- Free OpenRouter models in `roles.yaml`: minimax-m3.1-flash:free (retired) and nemotron-3-super:free (404) replaced.
- Tests block the network with `--allow-hosts=127.0.0.1,::1` instead of `--disable-socket`: asyncio needs a local
  socket pair (TCP on Windows); any external connection still fails.
- `runs` gets reproducibility fields (config jsonb, seed, package_version, tokens, timestamps); ER diagram in 04_data updated.
- CLAUDE.md: commands split into working now and arriving with tasks T-004, T-101, T-105, T-507 (T-002).
- `scripts/doctor.py` and `scripts/github_bootstrap.py` formatted with ruff (line length 100), no behaviour change.
- Core and experiments moved to ready-made tools: T-005 (pydantic-ai), T-006/T-304/T-405 (pydantic-evals),
  T-106 (pm4py with a DSL adapter), T-401/T-402 (pandoc).
- ADR-003 refined by ADR-013. ADR-015 (single Streamlit demo) was proposed and then rejected by the author:
  the web stack stays Next.js + FastAPI + worker + Vercel + Render + Supabase (ADR-001, 007, 008, 009).
- Model roles in 06_models updated to models verified on 2026-10-21; Cerebras removed.
