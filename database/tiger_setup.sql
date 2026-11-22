-- Tiger Class Drive: complete Supabase setup.
-- Paste this whole file into Supabase > SQL Editor > Run. It is safe to run more than once.

-- Profiles ------------------------------------------------------------------
create table if not exists public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  username   text,
  email      text,
  gpa        numeric(3, 2) check (gpa >= 0 and gpa <= 4.3),
  courses    jsonb not null default '[]',
  updated_at timestamptz not null default now()
);

alter table public.profiles
  add column if not exists completed_credit_hours integer not null default 0
  check (completed_credit_hours >= 0);

-- Usernames identify students to friends, so they must be unique ignoring case.
create unique index if not exists profiles_username_key
  on public.profiles (lower(username));

-- Every account gets a profile row, so schedules and friends work before the
-- student fills in their profile.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Accounts created before this trigger existed.
insert into public.profiles (id, email)
select id, email from auth.users
on conflict (id) do nothing;

-- Schedules -----------------------------------------------------------------
create table if not exists public.schedules (
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

alter table public.schedules
  add column if not exists color text not null default 'blue';

-- Forecasts -----------------------------------------------------------------
create table if not exists public.forecasts (
  user_id    uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  result     jsonb not null,
  updated_at timestamptz not null default now()
);

-- Friends and sharing -------------------------------------------------------
create table if not exists public.friendships (
  id           uuid primary key default gen_random_uuid(),
  requester_id uuid not null references public.profiles (id) on delete cascade,
  addressee_id uuid not null references public.profiles (id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'accepted')),
  created_at   timestamptz not null default now(),
  check (requester_id <> addressee_id),
  unique (requester_id, addressee_id)
);

create table if not exists public.schedule_shares (
  id          uuid primary key default gen_random_uuid(),
  schedule_id uuid not null references public.schedules (id) on delete cascade,
  owner_id    uuid not null references public.profiles (id) on delete cascade,
  friend_id   uuid not null references public.profiles (id) on delete cascade,
  created_at  timestamptz not null default now(),
  unique (schedule_id, friend_id),
  check (owner_id <> friend_id)
);

-- Lets a student find another account by exact username without reading profiles.
create or replace function public.profile_id_for_username(name text)
returns uuid
language sql
security definer
set search_path = public
as $$
  select id from public.profiles where lower(username) = lower(name) limit 1;
$$;

-- Usernames of the students linked to the caller by a friendship or request.
-- Profiles stay private; this exposes only id and username to the two people
-- involved, so the Friends page can show who sent a request.
create or replace function public.friend_profiles()
returns table (id uuid, username text)
language sql
stable
security definer
set search_path = public
as $$
  select p.id, p.username
  from public.profiles p
  where exists (
    select 1 from public.friendships f
    where (f.requester_id = auth.uid() and f.addressee_id = p.id)
       or (f.addressee_id = auth.uid() and f.requester_id = p.id)
  );
$$;

-- Only signed-in students may look up usernames.
revoke all on function public.profile_id_for_username(text) from public, anon;
grant execute on function public.profile_id_for_username(text) to authenticated;
revoke all on function public.friend_profiles() from public, anon;
grant execute on function public.friend_profiles() to authenticated;

-- Row level security --------------------------------------------------------
alter table public.profiles        enable row level security;
alter table public.schedules       enable row level security;
alter table public.forecasts       enable row level security;
alter table public.friendships     enable row level security;
alter table public.schedule_shares enable row level security;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- Friends see only each other's username, through friend_profiles(), never
-- the whole profile row (GPA, courses, email).
drop policy if exists "friends read profiles" on public.profiles;

drop policy if exists "own schedules" on public.schedules;
create policy "own schedules" on public.schedules
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "read schedules shared with me" on public.schedules;
create policy "read schedules shared with me" on public.schedules
  for select to authenticated using (
    exists (
      select 1 from public.schedule_shares sh
      where sh.schedule_id = schedules.id and sh.friend_id = auth.uid()
    )
    and exists (
      select 1 from public.friendships f
      where f.status = 'accepted'
      and ((f.requester_id = auth.uid() and f.addressee_id = schedules.user_id)
        or (f.addressee_id = auth.uid() and f.requester_id = schedules.user_id))
    )
  );

drop policy if exists "own forecast" on public.forecasts;
create policy "own forecast" on public.forecasts
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "view own friendships" on public.friendships;
create policy "view own friendships" on public.friendships
  for select to authenticated using (requester_id = auth.uid() or addressee_id = auth.uid());

drop policy if exists "send friend requests" on public.friendships;
create policy "send friend requests" on public.friendships
  for insert to authenticated with check (requester_id = auth.uid() and status = 'pending');

drop policy if exists "accept friend requests" on public.friendships;
create policy "accept friend requests" on public.friendships
  for update to authenticated
  using (addressee_id = auth.uid() and status = 'pending')
  with check (addressee_id = auth.uid() and status = 'accepted');

drop policy if exists "remove friendships" on public.friendships;
create policy "remove friendships" on public.friendships
  for delete to authenticated using (requester_id = auth.uid() or addressee_id = auth.uid());

drop policy if exists "view own schedule shares" on public.schedule_shares;
create policy "view own schedule shares" on public.schedule_shares
  for select to authenticated using (owner_id = auth.uid() or friend_id = auth.uid());

drop policy if exists "share own schedule with accepted friends" on public.schedule_shares;
create policy "share own schedule with accepted friends" on public.schedule_shares
  for insert to authenticated with check (
    owner_id = auth.uid()
    and exists (
      select 1 from public.schedules s
      where s.id = schedule_id and s.user_id = auth.uid()
    )
    and exists (
      select 1 from public.friendships f
      where f.status = 'accepted'
      and ((f.requester_id = auth.uid() and f.addressee_id = friend_id)
        or (f.addressee_id = auth.uid() and f.requester_id = friend_id))
    )
  );

drop policy if exists "stop sharing own schedules" on public.schedule_shares;
create policy "stop sharing own schedules" on public.schedule_shares
  for delete to authenticated using (owner_id = auth.uid());

-- Make the new tables visible to the API immediately.
notify pgrst, 'reload schema';
