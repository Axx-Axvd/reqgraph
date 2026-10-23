-- T-004 · row level security: everything is reachable only through projects.owner_id = auth.uid().
-- Writes to runs, run_events, graph_revisions, interview_turns, exports and usage_daily are done
-- by the backend with service_role (bypasses RLS); users get no insert/update policies there.

alter table public.profiles        enable row level security;
alter table public.projects        enable row level security;
alter table public.graph_revisions enable row level security;
alter table public.runs            enable row level security;
alter table public.run_events      enable row level security;
alter table public.interview_turns enable row level security;
alter table public.exports         enable row level security;
alter table public.usage_daily     enable row level security;

create policy own_select on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy own_update on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy owner_all on public.projects for all to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create policy via_project on public.graph_revisions for select to authenticated
  using (exists (select 1 from public.projects p
                 where p.id = graph_revisions.project_id and p.owner_id = (select auth.uid())));

create policy via_project on public.runs for select to authenticated
  using (exists (select 1 from public.projects p
                 where p.id = runs.project_id and p.owner_id = (select auth.uid())));

create policy via_project on public.exports for select to authenticated
  using (exists (select 1 from public.projects p
                 where p.id = exports.project_id and p.owner_id = (select auth.uid())));

create policy via_run on public.run_events for select to authenticated
  using (exists (select 1 from public.runs r join public.projects p on p.id = r.project_id
                 where r.id = run_events.run_id and p.owner_id = (select auth.uid())));

create policy via_run on public.interview_turns for select to authenticated
  using (exists (select 1 from public.runs r join public.projects p on p.id = r.project_id
                 where r.id = interview_turns.run_id and p.owner_id = (select auth.uid())));

create policy own_select on public.usage_daily for select to authenticated
  using (user_id = (select auth.uid()));

-- Live progress and the interview chat in the browser (07_deploy: Realtime).
alter publication supabase_realtime add table public.run_events, public.interview_turns;
