# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
