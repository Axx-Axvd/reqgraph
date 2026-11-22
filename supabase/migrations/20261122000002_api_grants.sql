-- T-506 · table rights of the API roles, stated explicitly. Supabase projects created since late 2026
-- no longer give anon, authenticated and service_role SELECT/INSERT/UPDATE/DELETE on new tables of
-- public (the local CLI still does): on prod the API got "permission denied for table jobs".
-- What a user may see or change is still decided by RLS (every table of public has it on).

grant usage on schema public to authenticated, service_role;

grant select, insert, update, delete on all tables in schema public to authenticated, service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;

-- tables and sequences of later migrations get the same rights
alter default privileges for role postgres in schema public
  grant select, insert, update, delete on tables to authenticated, service_role;
alter default privileges for role postgres in schema public
  grant usage, select on sequences to authenticated, service_role;
