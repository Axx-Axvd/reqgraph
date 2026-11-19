-- T-503 · limits of the public demo (07_deploy): a day in Moscow time (author's decision 19.11),
-- runs on a user's own key marked, and the total spent today for the API only.
alter table public.usage_daily
  alter column day set default ((now() at time zone 'Europe/Moscow')::date);

-- A run on the user's own OpenRouter key (BYOK): not counted in the demo limits, not in our spend.
alter table public.runs
  add column byok boolean not null default false;

-- All users' spend today: only the backend sees it, a user sees only their own row (RLS).
create function public.demo_spent_today(tz text default 'Europe/Moscow') returns numeric
language sql stable security definer set search_path = '' as $$
  select coalesce(sum(cost_usd), 0) from public.usage_daily
  where day = (now() at time zone tz)::date
$$;
revoke execute on function public.demo_spent_today(text) from public, anon, authenticated;
grant execute on function public.demo_spent_today(text) to service_role;
