# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The simulated client's understanding of IT (T-316): a 0-3 scale (not related to IT, a confident user, has
  ordered IT projects, a specialist), a level per persona and per area (`it_level`, `it_by_area` in
  `persona.yaml`, both optional; 3 by default, as before). A term of `sim/jargon.yaml` above the level without an
  example is not understood: nothing is told and the client asks what it means; with an example the client
  answers in general words only. `reqgraph-evals matrix|interview --it-level`; the level and the «not
  understood» answers go to results.csv and the dialogs. Level 3 behaves as the simulator did.
- `reqgraph-evals matrix --resume <progress.jsonl>` (T-406): each finished case is written to a progress file
  as it ends; a launch stopped by a container restart goes on from it, skips the saved cases and runs the
  failed ones again. Needed for the dev matrix on the cheap profile, run one scenario a day for the
  embeddings quota.
- B1 one-shot prompt (T-405): states the step types, the start event and foreign keys by table name, as the
  Modeler's prompt does; before, every B1 process and ERD of the smoke runs was dropped on format (author's
  decision of 2026-11-04). The kept B1 project holds the model's raw answer (`reports/oneshot.json`).
- The pilot «a person instead of the simulator» (T-306): `reqgraph-evals human card|start|answer|finish|page` —
  a person answers the interviewer from the scenario's card (persona, brief, the cooperative simulator's rules,
  hidden requirements by area), one turn per call, the interview waiting in its checkpoint between calls; optional
  marks of what was told are checked against the scenario; the result is a row in the simulator's interview format
  (method `M2-human`) read by `reqgraph-evals metrics`, and a dialog. The page `evals/human/page.html` is a
  claude.ai artifact: it stores the answer in its database and wakes the Claude session, which runs the interview
  (the model keys live there) and writes the next question back.
- A dollar limit for a matrix run (T-406): `reqgraph-evals matrix --max-usd` (1.0 by default, over 5 only with
  `--allow-over-5`) starts no case once the runs, the simulator and the judge have spent it; each case left is a
  row with the reason. `results-*.md` ends with a summary by method — means over the runs without an error, money
  and time over all — and Mermaid bar charts of recall and $. The command refuses test scenarios before anything
  runs. The experiments run in a Claude cloud session, not in GitHub Actions: the model keys live in the cloud
  environment (author's decision of 2026-11-03), so there is no evals.yml or probe.yml.
- Baselines of the matrix (T-405): `reqgraph-evals matrix --methods` runs M2, M1, B1 (one request on the brief and
  the M1 interview of the same case, built by the agents' code without checks), B2 (the agents without the repair
  loop and without their self-checks), B3 (a fixed questionnaire of 12 questions, `interviewer/questionnaire.md`,
  then the M1 pipeline) and the ablations A1-A3 (no repair, no TRC-*, template Reviewer); the scenario,
  character, simulator seed, model ladder and budget are the same for all. Core: `RunContext.interviewer =
  "questionnaire"` and `RunContext.self_checks`.
- `reqgraph-evals analyst` (T-311): requirements by kind, the reasons of dropped items, the facts of the brief kept
  (`in_brief` of hidden.yaml, the T-304 recall with the judge; its calls and cost apart), the T-311 rule per brief
  in the summary; `--save-runs` keeps the requirements of every run.
- ReqIF export (T-403): `reqgraph export` writes `exports/req.reqif` with the documents (`--doc reqif` alone needs
  no schemes and no pandoc). Sections by kind; every BR/UR/FR/NFR/CON with id, name, statement, status, priority,
  acceptance, metric, scenario, goal, realized_by, depends_on, conflicts_with; refines is the Parent relation.
  Text is XHTML: StrictDoc 0.30.4 breaks UTF-8 Cyrillic in plain strings. Valid by the ReqIF 1.2 XSD; StrictDoc
  imports garage61 and a dev-01 run without errors. New dependency `reqif` 0.1.0 (Apache-2.0, by the StrictDoc
  authors; pulls `openpyxl` and `xmlschema`), imported lazily.
- Modeler draws use cases and C4 (T-207): a second question to the model fills a form (use cases with their
  role, FRs and extends / includes; the system, its containers, external systems and relationships); code writes
  `models/uml/use_cases.puml` and `models/c4/workspace.dsl` (`dsl/plantuml.py`, `dsl/c4.py`: read and build both
  in the conventions of garage61), issues UC and C4 ids and the realized_by links. Self-check of at most 3 answers:
  SCH-004, SCH-005 (Kroki), TRC-003 among UC and C4, a use case for every role, a C4 model; repair tasks on UC and
  C4 go to this question. Role `modeler_views` in `llm/roles.yaml` (the Modeler's ladder);
  `reqgraph-evals uml` measures it on the dev briefs. The live Modeler and dev-01 run cassettes are re-recorded.
- TZ for a program by GOST 19.201-78 (T-407): `reqgraph export --doc tz19` (or `gost19_201` in
  `project.standards`) writes `exports/tz_gost19.md|docx` from the same graph and schemes; the structure
  `standards/gost19_201.yaml` has the eight sections of the standard with their contents as subsections and
  appendices A (models) and B (traceability), names only, to be checked by the author. TPL-003 checks its required
  sections. **Public schema `project-config` stays version 1:** `project.standards` accepts `gost19_201` in
  addition, every earlier `reqgraph.yaml` stays valid, nothing to migrate.
- TZ by GOST 34.602-2020 (T-402): `reqgraph export` writes `exports/tz_gost34.md|docx` next to the SRS from the same
  graph (`--doc srs,tz`, by default `project.standards`); the structure `standards/gost34_602.yaml` has every
  section of the standard (names only, to be checked by the author); NFR, constraints, C4 elements and functions go
  to the GOST sections, the Standards text comes from the SRS sections, contract sections and sections that do
  not apply say so. TPL-002 checks its required sections (T-404); TPL-001 and TPL-002 share one check.
- SRS export (T-401): `reqgraph export <project>` writes `exports/srs.md` and `exports/srs.docx` by
  `standards/iso29148_srs.yaml` — sections with ids, a traceability appendix (FR → UR → BR → model elements),
  every BPMN scheme on a landscape A4 page of its own (Kroki; `--offline` reads only the cache). DOCX through pandoc
  (`pypandoc-binary` 1.17, ADR-016) with `exporters/templates/reference.docx` built by
  `scripts/make_reference_docx.py` (A4, GOST margins, Times New Roman).
- Requirements retold from the PURE set in the dev references (T-307): dev-01 5 from the microcare SRS, dev-02 4 from
  e-store, dev-03 5 from library, each with `source: PURE:<document>#<section or Req ID>` and a typical / unique
  label; the template and the order for the test references (Claude, at the start of S6) are in the scenarios'
  README. The dev references grew (25, 32 and 49 hidden requirements outside the brief).
- Per-model request parameters in `roles.yaml` (`model_settings`, T-310), sent as `extra_body`. The simulator and
  the judge (Qwen3.8-27B on OpenRouter) run without reasoning: in a measurement of three modes the simulator named
  as many hidden requirements and the judge agreed with the author's labels as well, at 1/6-1/7 of the cost.
  `simprobe --reasoning` and the new `judgeprobe` (the judge again on the author's labelled references) measure it.
- Typical and unique hidden requirements (T-308): an optional `group` of a hidden requirement, the labelling
  rule in `evals/scenarios/README.md` (written before the labels), the dev references labelled; the scenario check
  wants every dev requirement labelled and a test reference all or none. `results-*.csv` gets hidden, matched and
  recall of each group, the interview report what the client told of each group.
  `reqgraph-evals groups` asks the labels one by one in the terminal and writes each answer at once; `--check`
  asks a second labeller on a seeded 20% sample with the first labels hidden and gives Cohen's kappa.
  The test references are labelled by Claude at the start of S6, before the first run of the matrix
  (author's decision of 2026-11-02).
- Simulator select step without repeats (T-309): the choice sees the hidden list split into untold (grouped by
  area) and told, and the brief counts as told; a broad question about an area may reveal up to three untold
  items; code keeps a repeat only when nothing new is picked. `python -m reqgraph_evals.simprobe` replays the
  select step on questions of the T-305 dialogs.
- Own price list in `roles.yaml` (`prices`): the cost of models genai-prices does not list (Qwen3.8-27B,
  DeepSeek V4 Flash on OpenRouter) is counted instead of a silent zero.

- Interviewer without repeats (T-305): an answer that yields no new requirement closes its area; every area gets
  a question before any is asked again, even one the brief covered; the interviewer sees the facts told about the
  areas it asks about and starts an area with a broad question; the interview ends as saturated when nothing is left
  to ask. `reqgraph-evals interview` counts questions whose answer told no hidden requirement anew.
- Metrics of the experiment (T-304): `evals/reqgraph_evals/metrics/` on pydantic-evals — a case is scenario ×
  character × method × repeat, evaluators score it. Recall: hidden requirements vs requirements found (not
  assumptions) — embeddings pick the top 3 candidates above 0.5, the judge (`prompts/judge/match.md`, another model
  family than the agents) decides; `recall` counts the hidden requirements outside the brief, `recall_all` the whole
  reference. Ambiguity, validity, soundness, trace coverage and orphan rate come from the deterministic checks.
  `results-*.csv` keeps the whole record of a run (models, temperatures, seed, prompt hashes, version, judge and
  embedding models, tokens, $, time) and every judged pair goes to `labels/pairs-*.csv`. Manual check of the judge:
  a seeded 20% sample of references (`reqgraph-evals label`), agreement and Cohen's kappa (`reqgraph-evals agreement`).
  The judge answers full / partial / none; on a fresh dev-03 sample labelled by the author, kappa of «full or not»
  is 0.858 (threshold 0.8).
  `reqgraph-evals metrics` scores saved interview runs, `reqgraph-evals matrix` runs and scores in one go.
  `llm/embed.py` — embeddings through pydantic-ai with a disk cache; `embeddings` in roles.yaml.

- Stakeholder simulator (T-302): `sim/stakeholder.py` — two steps per answer: `select` (the model sees the hidden
  list and picks at most 3 requirements the question is about, code checks the ids) and `reply` (the answer in the
  persona's manner; the model sees only the picked ones, so it cannot give away others); already told requirements
  are repeated, not forgotten; characters in code — vague (only the topic first, details on a follow-up),
  contradictory (a seeded wrong quantity, corrected when the talk comes back to its area); `sim/scenario.py`
  (scenario models moved from evals). `reqgraph-evals interview` — the interviewer against the simulator, a CSV row
  per run, readable dialogs for the manual check, the run projects for T-304. `llm/prompts.py` — one Jinja2
  loader for agents and the simulator; `role_settings` in roles.yaml (the simulator answers at 0.7).

- `reqgraph interview` (T-301): the interview in the terminal with pause and resume. The Analyst reads every answer
  right away (only the new turns), `agents/coverage.py` counts the coverage of the 9 areas from the graph
  (requirements derived from client turns and not assumptions; actors; distinct ISO 25010 characteristics), the
  `coverage` node decides on the next question; the interviewer (`prompts/interviewer/ask.md`) asks about the
  emptiest areas and moves on after two questions about one area; `--interviewer free` (no tracker, method M1).
  State is checkpointed into the project folder (`.reqgraph/checkpoints.sqlite`, new dependency
  `langgraph-checkpoint-sqlite` 3.1.2, MIT); «/готово» ends the interview, «/пауза» or Ctrl+C pauses it.
  `agents/interview.py` (`interview_project()` with an answer callback, used by the simulator in T-302);
  `RunSummary.turns`; `RunState.interview_done`, `extracted_upto`, `asked_areas`.
- Scenarios of the experiment (T-303): `evals/scenarios/` — 3 dev and 12 test scenarios (brief, persona, hidden
  requirements: 25 / 40 / 60 per size, all 9 coverage areas, `in_brief` marks what the brief already says);
  `reqgraph_evals/scenario.py` (schemas, loader that refuses test scenarios without `final=True`, protocol checks,
  the SHA-256 seal of test files); `reqgraph-evals scenarios [--seal]`. Drafts by Claude, to be checked by the author.
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

- TZ (T-314): a constraint goes to the TZ sections by its type (time, budget, legal, tech) that the Analyst sets,
  not by words of its text: «stored in Russia» landed nowhere, «on the university servers» in two sections.
- Analyst (T-313): atomic FRs — the prompt says one function, one FR, with an example of a list of functions
  against a list of one object's properties; an FR with two actions by the ISO-002 heuristic
  (`checks.iso.two_actions`, shared with the check) is a reason for the retry. On the dev briefs the worst of five
  repeats now keeps 81-100% of the brief facts (75% before) and fewer FRs carry ISO-002.
- Analyst (T-311): a user requirement that no FR refines and an FR without acceptance criteria are reasons for
  its one retry, and the better of the two answers is applied (a UR without FRs costs three times other problems).
  On one dev brief the FR count of five repeats went from 2-11 to 6-10.
- Export: figures are numbered by the appendix they are in; the TZ by GOST 34.602 had «Рисунок Б.n» in
  appendix A (T-407).
- LLM ladder: a provider that blocks an answer (Gemini `finish_reason: content_filter: PROHIBITED_CONTENT` on an
  ordinary repair prompt) no longer ends the run; the next model of the ladder answers.
- `structured()` waits and asks again when every model of a ladder answers 429 (free tiers count tokens per
  minute); an interview goes on when the Analyst's ladder fails on one answer (the turns stay unread).
- Interview coverage: a BR counts as a goal and a CON as a constraint whatever the Analyst's area tag; the
  Analyst prompt explains the areas of UR and FR.

- Checkpoints restored edges with a warning (`Rel` was not in the msgpack allow-list); now allowed and tested.
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

- Dev references (T-312): the facts of the brief (`in_brief`) say only what the brief says — dev-01 H-011, dev-03
  H-051 and H-052 lose details the brief does not give, dev-02 H-034 keeps the brief's 120 orders and the
  300 visitors become a new hidden H-045. Interview recall on dev-02 before and after is not comparable
  (33 hidden requirements instead of 32).
- SRS structure after Wiegers and Beatty (IEEE 830) instead of the own list after ISO/IEC/IEEE 29148 (T-408):
  introduction, overall description, system features (a user requirement with its stimulus / response
  sequence and FRs), external interfaces, NFR by ISO 25010 characteristic, other requirements, appendices
  glossary, analysis models (every scheme of the project: BPMN, ER, UML, C4), issues, acceptance criteria,
  traceability; sections keep their English originals (`title_en`). Standards writes 13 text fields
  (purpose, scope, perspective and glossary required). The value `standards: [iso29148]` is unchanged.
- Document sections (SEC) are kept in `documents/<template>.yaml` of the project (T-401): the Standards text
  survives saving; TPL-001 builds list sections from the graph and reads only the LLM text from the stored sections.
- Simulator and judge run on Qwen3.8-27B through OpenRouter (paid) with Groq as the free reserve, and on the same
  model in profile `cheap` instead of Llama 3.3 70B and GLM-5.3 Flash (author's decision of 2026-11-02, after a
  probe of four models in the simulator's select step).

- README rewritten for any visitor, in a plain professional style: purpose, approach, how it works, what changes,
  evaluation, project status; English is the main `README.md`, the Russian version is
  `README.ru.md`, with a language switch at the top of both.
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
