-- Friend requests and accepted friendships
create table if not exists public.friendships (
    id uuid primary key default gen_random_uuid(),
    requester_id uuid not null references public.profiles(id) on delete cascade,
    addressee_id uuid not null references public.profiles(id) on delete cascade,
    status text not null default 'pending'
        check (status in ('pending', 'accepted')),
    created_at timestamptz not null default now(),
    check (requester_id <> addressee_id),
    unique (requester_id, addressee_id)
);

-- Explicit permissions to share a schedule
create table if not exists public.schedule_shares (
    id uuid primary key default gen_random_uuid(),
    schedule_id uuid not null references public.schedules(id) on delete cascade,
    owner_id uuid not null references public.profiles(id) on delete cascade,
    friend_id uuid not null references public.profiles(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (schedule_id, friend_id),
    check (owner_id <> friend_id)
);

alter table public.friendships enable row level security;
alter table public.schedule_shares enable row level security;

-- Students can see requests involving their own account
create policy "view own friendships"
on public.friendships for select to authenticated
using (requester_id = auth.uid() or addressee_id = auth.uid());

-- Students can send requests only from their own account
create policy "send friend requests"
on public.friendships for insert to authenticated
with check (requester_id = auth.uid() and status = 'pending');

-- Only the recipient can accept requests
create policy "accept friend requests"
on public.friendships for update to authenticated
using (addressee_id = auth.uid() and status = 'pending')
with check (addressee_id = auth.uid() and status = 'accepted');

-- Either participant can remove a friendship or request
create policy "remove friendships"
on public.friendships for delete to authenticated
using (requester_id = auth.uid() or addressee_id = auth.uid());

-- Owners can see and manage their sharing permissions
create policy "view own schedule shares"
on public.schedule_shares for select to authenticated
using (owner_id = auth.uid() or friend_id = auth.uid());

create policy "share own schedule with accepted friends"
on public.schedule_shares for insert to authenticated
with check (
    owner_id = auth.uid()
    and exists (
        select 1 from public.schedules s
        where s.id = schedule_id and s.user_id = auth.uid()
    )
    and exists (
        select 1 from public.friendships f
        where f.status = 'accepted'
        and (
            (f.requester_id = auth.uid() and f.addressee_id = friend_id)
            or (f.addressee_id = auth.uid() and f.requester_id = friend_id)
        )
    )
);

create policy "stop sharing own schedules"
on public.schedule_shares for delete to authenticated
using (owner_id = auth.uid());

-- Accepted friends can read schedules that were explicitly shared with them.
create policy "read schedules shared with me"
on public.schedules for select to authenticated
using (
    exists (
        select 1 from public.schedule_shares sh
        where sh.schedule_id = schedules.id and sh.friend_id = auth.uid()
    )
    and exists (
        select 1 from public.friendships f
        where f.status = 'accepted'
        and (
            (f.requester_id = auth.uid() and f.addressee_id = schedules.user_id)
            or (f.addressee_id = auth.uid() and f.requester_id = schedules.user_id)
        )
    )
);

-- Accepted friends can read each other's profile row (needed for usernames).
create policy "friends read profiles"
on public.profiles for select to authenticated
using (
    exists (
        select 1 from public.friendships f
        where f.status = 'accepted'
        and (
            (f.requester_id = auth.uid() and f.addressee_id = profiles.id)
            or (f.addressee_id = auth.uid() and f.requester_id = profiles.id)
        )
    )
);
