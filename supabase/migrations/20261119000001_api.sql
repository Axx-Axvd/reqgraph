-- T-501 · what the API needs to store a whole project and to queue runs for the worker (T-502).
-- A FileStore project folder maps to: projects.config (reqgraph.yaml), graph_revisions.graph,
-- graph_revisions.files (model texts as read) and graph_revisions.layout (node id -> file).

alter table public.projects
  add column config jsonb not null default '{}';

alter table public.graph_revisions
  add column files  jsonb not null default '{}',
  add column layout jsonb not null default '{}';

-- ADR-009: the job queue in Postgres; the worker takes jobs with FOR UPDATE SKIP LOCKED.
-- start — a new run; resume — the answer to an interview question; cancel — stop the run.
create table public.jobs (
  id         bigint generated always as identity primary key,
  run_id     uuid not null references public.runs (id) on delete cascade,
  kind       text not null check (kind in ('start', 'resume', 'cancel')),
  payload    jsonb not null default '{}',
  status     text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed')),
  attempts   int not null default 0,
  locked_at  timestamptz,
  created_at timestamptz not null default now()
);
create index jobs_queue_idx on public.jobs (status, id);
create index jobs_run_idx on public.jobs (run_id);

-- Backend only: RLS on and no policy, so users see nothing (the API writes with its own role).
alter table public.jobs enable row level security;
