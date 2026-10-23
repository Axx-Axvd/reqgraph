-- RLS tests (T-004): a user sees only their own projects and everything under them.
-- Run: pnpm db:test  (supabase test db, pgTAP). Data is created inside the transaction and rolled back.
begin;
create extension if not exists pgtap with schema extensions;

select plan(17);

-- Two users; the auth trigger creates their profiles.
insert into auth.users (id, email, aud, role)
values ('00000000-0000-4000-8000-0000000000a1', 'alice-test@example.invalid', 'authenticated', 'authenticated'),
       ('00000000-0000-4000-8000-0000000000b1', 'bob-test@example.invalid', 'authenticated', 'authenticated');

select is((select count(*)::int from public.profiles
           where id in ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-0000000000b1')),
          2, 'профили создаются триггером при регистрации');

-- Backend (service role, RLS bypass) creates data for both users.
insert into public.projects (id, owner_id, name)
values ('00000000-0000-4000-8000-00000000a0a1', '00000000-0000-4000-8000-0000000000a1', 'alice project'),
       ('00000000-0000-4000-8000-00000000b0b1', '00000000-0000-4000-8000-0000000000b1', 'bob project');
insert into public.graph_revisions (project_id, rev, graph, author)
values ('00000000-0000-4000-8000-00000000a0a1', 1, '{}', 'agent'),
       ('00000000-0000-4000-8000-00000000b0b1', 1, '{}', 'agent');
insert into public.runs (id, project_id, kind, status)
values ('00000000-0000-4000-8000-0000000a7001', '00000000-0000-4000-8000-00000000a0a1', 'interview', 'running'),
       ('00000000-0000-4000-8000-0000000b7001', '00000000-0000-4000-8000-00000000b0b1', 'interview', 'running');
insert into public.run_events (run_id, type, payload)
values ('00000000-0000-4000-8000-0000000a7001', 'node', '{}'),
       ('00000000-0000-4000-8000-0000000b7001', 'node', '{}');
insert into public.interview_turns (run_id, role, content)
values ('00000000-0000-4000-8000-0000000a7001', 'agent', 'вопрос'),
       ('00000000-0000-4000-8000-0000000b7001', 'agent', 'вопрос');
insert into public.exports (project_id, rev, format, storage_path)
values ('00000000-0000-4000-8000-00000000a0a1', 1, 'srs-docx', 'a/srs.docx'),
       ('00000000-0000-4000-8000-00000000b0b1', 1, 'srs-docx', 'b/srs.docx');
insert into public.usage_daily (user_id, day, runs)
values ('00000000-0000-4000-8000-0000000000a1', current_date, 1),
       ('00000000-0000-4000-8000-0000000000b1', current_date, 1);

-- Every table in public has RLS enabled (guards against a new table without policies).
select is((select count(*)::int from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity),
          0, 'RLS включён на всех таблицах public');

-- Act as alice. Both settings are set: `supabase db start` runs Postgres without the auth service,
-- whose migrations switch auth.uid() from request.jwt.claim.sub to request.jwt.claims.
set local role authenticated;
select set_config('request.jwt.claims', '{"sub": "00000000-0000-4000-8000-0000000000a1", "role": "authenticated"}', true);
select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000000a1', true);

select results_eq('select name from public.projects', $$values ('alice project'::text)$$,
                  'alice видит только свой проект');
select is((select count(*)::int from public.profiles), 1, 'alice видит только свой профиль');
select is((select count(*)::int from public.graph_revisions), 1, 'ревизии чужого проекта не видны');
select is((select count(*)::int from public.runs), 1, 'прогоны чужого проекта не видны');
select is((select count(*)::int from public.run_events), 1, 'события чужого прогона не видны');
select is((select count(*)::int from public.interview_turns), 1, 'реплики чужого интервью не видны');
select is((select count(*)::int from public.exports), 1, 'выгрузки чужого проекта не видны');
select is((select count(*)::int from public.usage_daily), 1, 'чужой расход не виден');

select lives_ok($$insert into public.projects (owner_id, name)
                  values ('00000000-0000-4000-8000-0000000000a1', 'alice second')$$,
                'alice создаёт свой проект');
select throws_ok($$insert into public.projects (owner_id, name)
                   values ('00000000-0000-4000-8000-0000000000b1', 'spoofed')$$,
                 '42501', null, 'проект от имени другого пользователя создать нельзя');

update public.projects set name = 'hacked' where id = '00000000-0000-4000-8000-00000000b0b1';
delete from public.projects where id = '00000000-0000-4000-8000-00000000b0b1';
select throws_ok($$insert into public.runs (project_id, kind, status)
                   values ('00000000-0000-4000-8000-00000000a0a1', 'interview', 'queued')$$,
                 '42501', null, 'прогоны пишет только backend');

-- Act as anon.
reset role;
set local role anon;
select set_config('request.jwt.claims', '{"role": "anon"}', true);
select set_config('request.jwt.claim.sub', '', true);
select is((select count(*)::int from public.projects), 0, 'anon не видит проекты');
select is((select count(*)::int from public.runs), 0, 'anon не видит прогоны');

-- Back to the owner role: bob's project survived alice's update and delete attempts.
reset role;
select is((select name from public.projects where id = '00000000-0000-4000-8000-00000000b0b1'),
          'bob project', 'чужой проект нельзя изменить или удалить');

-- Cascade: deleting a project removes its revisions, runs and events.
delete from public.projects where id = '00000000-0000-4000-8000-00000000a0a1';
select is((select count(*)::int from public.run_events where run_id = '00000000-0000-4000-8000-0000000a7001'),
          0, 'удаление проекта каскадно удаляет прогоны и события');

select * from finish();
rollback;
