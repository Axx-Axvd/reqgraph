-- Local stand only (supabase db reset). Fictional users, no real data.
-- Passwords are not set: sign in locally with a magic link (Inbucket, http://127.0.0.1:54324).
-- Only columns of the base auth.users table: in CI `supabase db start` runs without the auth service.
insert into auth.users (id, instance_id, email, aud, role, raw_user_meta_data)
values
  ('00000000-0000-4000-8000-00000000a11c', '00000000-0000-0000-0000-000000000000',
   'alice@example.invalid', 'authenticated', 'authenticated', '{"display_name": "Алиса (демо)"}'),
  ('00000000-0000-4000-8000-000000000b0b', '00000000-0000-0000-0000-000000000000',
   'bob@example.invalid', 'authenticated', 'authenticated', '{"display_name": "Боб (демо)"}');

insert into public.projects (owner_id, name)
values ('00000000-0000-4000-8000-00000000a11c', 'Гараж 61 (демо)'),
       ('00000000-0000-4000-8000-000000000b0b', 'Чужой проект (демо)');
