# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- `scripts/doctor.py` and `scripts/github_bootstrap.py` formatted with ruff (line length 100), no behaviour change.
- Core and experiments moved to ready-made tools: T-005 (pydantic-ai), T-006/T-304/T-405 (pydantic-evals),
  T-106 (pm4py with a DSL adapter), T-401/T-402 (pandoc).
- ADR-003 refined by ADR-013. ADR-015 (single Streamlit demo) was proposed and then rejected by the author:
  the web stack stays Next.js + FastAPI + worker + Vercel + Render + Supabase (ADR-001, 007, 008, 009).
- Model roles in 06_models updated to models verified on 2026-10-21; Cerebras removed.
