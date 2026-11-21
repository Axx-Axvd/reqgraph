-- T-505 · what the site needs to show the checks and hand out the exported documents.

-- The whole CI report of a revision (CIReport JSON, as `reqgraph check --json`): the site
-- highlights the nodes of a finding. ci_summary keeps only the counts.
alter table public.graph_revisions
  add column ci_report jsonb;

-- One row per exported file of a revision; a repeated export of the same revision reuses them.
alter table public.exports
  add constraint exports_file_key unique (project_id, rev, storage_path);

-- Private bucket for the exported files (SRS, TZ, ReqIF, scheme pictures). Path:
-- <project id>/<rev>/<file>. Only the API writes (service_role bypasses RLS).
insert into storage.buckets (id, name, public)
values ('exports', 'exports', false)
on conflict (id) do nothing;

-- The owner of the project reads its files (signed links are made by the site under this policy).
create policy exports_owner_read on storage.objects for select to authenticated
  using (
    bucket_id = 'exports'
    and exists (
      select 1 from public.projects p
      where p.id::text = (storage.foldername(objects.name))[1]
        and p.owner_id = (select auth.uid())
    )
  );
