-- NOTE: database/tiger_setup.sql is the complete, re-runnable setup. Prefer it.
-- Tiger Class Drive schema: profiles and saved schedules.

create table public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  username   text,
  email      text,
  gpa        numeric(3, 2) check (gpa >= 0 and gpa <= 4.3),
  courses    jsonb not null default '[]',
  updated_at timestamptz not null default now()
);

create table public.schedules (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name        text not null,
  semester    text not null,
  color       text not null default 'blue',
  sections    jsonb not null default '[]',
  commitments jsonb not null default '[]',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

alter table public.profiles  enable row level security;
alter table public.schedules enable row level security;

create policy "own profile" on public.profiles
  for all to authenticated using (id = auth.uid()) with check (id = auth.uid());

create policy "own schedules" on public.schedules
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create table public.friend_requests (
  id                 uuid primary key default gen_random_uuid(),
  sender_id          uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  recipient_id       uuid not null references public.profiles (id) on delete cascade,
  sender_username    text not null,
  recipient_username text not null,
  status             text not null default 'pending' check (status = 'pending'),
  created_at         timestamptz not null default now(),
  check (sender_id <> recipient_id),
  unique (sender_id, recipient_id)
);

alter table public.friend_requests enable row level security;

-- Only the two accounts involved can see a request; only the sender can create it.
create policy "see own requests" on public.friend_requests
  for select to authenticated using (sender_id = auth.uid() or recipient_id = auth.uid());

create policy "send as self" on public.friend_requests
  for insert to authenticated with check (sender_id = auth.uid());

-- Lets a student find another account by username without reading other profiles.
create or replace function public.profile_id_for_username(name text)
returns uuid
language sql
security definer
set search_path = public
as $$
  select id from public.profiles where lower(username) = lower(name) limit 1;
$$;

-- Only signed-in students may look up usernames.
revoke all on function public.profile_id_for_username(text) from public, anon;
grant execute on function public.profile_id_for_username(text) to authenticated;

-- For databases created before completed credit hours were saved.
alter table public.profiles
  add column if not exists completed_credit_hours integer not null default 0
  check (completed_credit_hours >= 0);

-- Usernames identify students to friends, so they must be unique ignoring case.
create unique index if not exists profiles_username_key
  on public.profiles (lower(username));

-- Schedule colour shown on the schedule page (for databases created earlier).
alter table public.schedules
  add column if not exists color text not null default 'blue';

-- One saved GPA forecast per student (shown on the dashboard).
create table if not exists public.forecasts (
  user_id    uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  result     jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.forecasts enable row level security;

drop policy if exists "own forecast" on public.forecasts;
create policy "own forecast" on public.forecasts
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
