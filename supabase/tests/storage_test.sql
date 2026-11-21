-- Storage tests (T-505): the exports bucket is private and its files are read by the project owner.
-- Run: pnpm db:test (supabase test db, pgTAP). Data is created inside the transaction and rolled back.
begin;
create extension if not exists pgtap with schema extensions;

select plan(5);

select is((select public from storage.buckets where id = 'exports'), false,
          'бакет exports есть и он закрытый');

insert into auth.users (id, email, aud, role)
values ('00000000-0000-4000-8000-0000000005a1', 'alice-storage@example.invalid', 'authenticated', 'authenticated'),
       ('00000000-0000-4000-8000-0000000005b1', 'bob-storage@example.invalid', 'authenticated', 'authenticated');
insert into public.projects (id, owner_id, name)
values ('00000000-0000-4000-8000-00000005a0a1', '00000000-0000-4000-8000-0000000005a1', 'alice project'),
       ('00000000-0000-4000-8000-00000005b0b1', '00000000-0000-4000-8000-0000000005b1', 'bob project');
-- The API uploads with the service role; here the rows are put in directly.
insert into storage.objects (bucket_id, name)
values ('exports', '00000000-0000-4000-8000-00000005a0a1/1/srs.docx'),
       ('exports', '00000000-0000-4000-8000-00000005a0a1/1/img/PRC-01.svg'),
       ('exports', '00000000-0000-4000-8000-00000005b0b1/1/srs.docx');

set local role authenticated;
select set_config('request.jwt.claims', '{"sub": "00000000-0000-4000-8000-0000000005a1", "role": "authenticated"}', true);
select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000005a1', true);

select is((select count(*)::int from storage.objects where bucket_id = 'exports'), 2,
          'владелец видит файлы своего проекта, чужие — нет');
select is((select count(*)::int from storage.objects
           where name like '00000000-0000-4000-8000-00000005b0b1/%'), 0,
          'файлы чужого проекта не видны');
select throws_ok($$insert into storage.objects (bucket_id, name)
                   values ('exports', '00000000-0000-4000-8000-00000005a0a1/1/x.md')$$,
                 '42501', null, 'пользователь не кладёт файлы в бакет: пишет только сервер');

select set_config('request.jwt.claims', '{"sub": "00000000-0000-4000-8000-0000000005b1", "role": "authenticated"}', true);
select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000005b1', true);
select is((select count(*)::int from storage.objects where bucket_id = 'exports'), 1,
          'другой пользователь видит только свой файл');

select * from finish();
rollback;
