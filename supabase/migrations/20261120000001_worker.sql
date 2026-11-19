-- T-502 · the worker: LangGraph checkpoints in their own schema and the outcome of every job.
-- AsyncPostgresSaver.setup() creates its tables in lg when the worker starts (04_data).
create schema if not exists lg;
revoke all on schema lg from public;
revoke all on schema lg from anon, authenticated;

alter table public.jobs
  add column error       text,
  add column finished_at timestamptz;
