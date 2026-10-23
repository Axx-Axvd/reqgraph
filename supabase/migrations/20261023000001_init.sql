-- T-004 · schema from docs/tech-design/04_data.md («Схема Supabase»).
-- New changes go into new migration files; applied migrations are never edited.
-- Schema lg (LangGraph checkpoints) is created by PostgresSaver.setup() in T-502.

-- Profiles mirror auth.users one-to-one.
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  role         text not null default 'user' check (role in ('user', 'admin')),
  created_at   timestamptz not null default now()
);

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

create table public.projects (
  id         uuid primary key default gen_random_uuid(),
  owner_id   uuid not null references public.profiles (id) on delete cascade,
  name       text not null check (length(name) between 1 and 200),
  standards  text[] not null default '{iso29148,gost34}',
  langs      text[] not null default '{ru}',
  head_rev   int not null default 0,
  created_at timestamptz not null default now()
);
create index projects_owner_idx on public.projects (owner_id);

-- Each applied GraphPatch -> a new revision; author = agent or user (manual edit in UI).
create table public.graph_revisions (
  id         bigint generated always as identity primary key,
  project_id uuid not null references public.projects (id) on delete cascade,
  rev        int not null,
  graph      jsonb not null,
  ci_summary jsonb,
  author     text not null check (author in ('agent', 'user')),
  created_at timestamptz not null default now(),
  unique (project_id, rev)
);

-- Reproducibility: counters and filters are columns, the rest of the run parameters
-- (models per role, provider, temperature, prompt hashes) go to config.
create table public.runs (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references public.projects (id) on delete cascade,
  kind            text not null check (kind in ('interview', 'brief', 'repair', 'export', 'eval')),
  status          text not null default 'queued'
                  check (status in ('queued', 'running', 'waiting_input', 'succeeded', 'failed', 'cancelled')),
  iteration       int not null default 0,
  model_profile   text,
  config          jsonb not null default '{}',
  seed            int,
  package_version text,
  tokens_in       bigint not null default 0,
  tokens_out      bigint not null default 0,
  cost_usd        numeric(10, 4) not null default 0,
  error           text,
  created_at      timestamptz not null default now(),
  started_at      timestamptz,
  finished_at     timestamptz
);
create index runs_project_idx on public.runs (project_id, created_at desc);

create table public.run_events (
  id      bigint generated always as identity primary key,
  run_id  uuid not null references public.runs (id) on delete cascade,
  type    text not null,
  payload jsonb not null default '{}',
  ts      timestamptz not null default now()
);
create index run_events_run_idx on public.run_events (run_id, id);

create table public.interview_turns (
  id         bigint generated always as identity primary key,
  run_id     uuid not null references public.runs (id) on delete cascade,
  role       text not null check (role in ('agent', 'client')),
  content    text not null,
  coverage   jsonb,
  created_at timestamptz not null default now()
);
create index interview_turns_run_idx on public.interview_turns (run_id, id);

create table public.exports (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects (id) on delete cascade,
  rev          int not null,
  format       text not null,
  storage_path text not null,
  created_at   timestamptz not null default now()
);
create index exports_project_idx on public.exports (project_id);

-- Demo limits (T-503): runs, tokens and dollars per user per day.
create table public.usage_daily (
  user_id    uuid not null references public.profiles (id) on delete cascade,
  day        date not null default current_date,
  runs       int not null default 0,
  tokens_in  bigint not null default 0,
  tokens_out bigint not null default 0,
  cost_usd   numeric(10, 4) not null default 0,
  primary key (user_id, day)
);
