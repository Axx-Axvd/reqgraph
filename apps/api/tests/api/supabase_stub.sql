-- The part of Supabase the migrations and the API rely on, for tests on a bare Postgres (T-501).
-- On a real Supabase (pnpm db:start in CI) none of this is applied: it is all there already.
do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end
$$;
grant anon, authenticated, service_role to current_user;

create schema auth;
create table auth.users (
  id                 uuid primary key,
  email              text,
  aud                text,
  role               text,
  raw_user_meta_data jsonb not null default '{}',
  created_at         timestamptz not null default now()
);
-- As in Supabase: the user id is the sub claim of the request's JWT.
create function auth.uid() returns uuid
language sql stable as $$
  select nullif(coalesce(current_setting('request.jwt.claim.sub', true),
                         (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')), '')::uuid
$$;

create publication supabase_realtime;

-- Storage (T-505): the tables and the helper the exports bucket and its policy use.
create schema storage;
create table storage.buckets (
  id     text primary key,
  name   text not null,
  public boolean not null default false
);
create table storage.objects (
  id         uuid primary key default gen_random_uuid(),
  bucket_id  text references storage.buckets (id),
  name       text not null,
  created_at timestamptz not null default now()
);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[]
language sql immutable as $$
  select (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'), 1) - 1]
$$;

grant usage on schema public, auth, storage to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
grant select on storage.objects, storage.buckets to authenticated;
grant all on storage.objects, storage.buckets to service_role;
