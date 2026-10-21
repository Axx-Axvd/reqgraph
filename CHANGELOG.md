# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Technical design, ADR 001–012, backlog and the garage61 reference project (draft).
- Preflight (stage 0): session prompts in `docs/prompts/`, development journal, GitHub templates,
  Dependabot, `.gitattributes`, `.editorconfig`, `scripts/doctor.py`, `scripts/github_bootstrap.py`,
  setup guides in `docs/setup/` and version research in `docs/research/`.
- ADR-013 (LLM layer on pydantic-ai), ADR-014 (soundness via pm4py with a DSL adapter),
  ADR-015 (single Streamlit demo, Supabase as Postgres only), ADR-016 (DOCX export via pandoc).

### Changed

- Backlog moved to ready-made tools: T-004 merged into T-503; E5 reduced from 7 to 5 tasks
  (T-501…T-505); T-005, T-006, T-106, T-304, T-401, T-402, T-405 use existing libraries.
- ADR-008 and ADR-009 superseded by ADR-015; ADR-001, ADR-003, ADR-007 narrowed.
- Model roles in 06_models updated to models verified on 2026-10-21; Cerebras removed.

### Removed

- Next.js, FastAPI, background worker, Vercel and Render from the plan; npm from Dependabot.
