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
