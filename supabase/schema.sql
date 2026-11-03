-- NathGPT : schéma Supabase. À exécuter une fois dans Supabase > SQL Editor > New query.
-- Le script peut être relancé sans risque : il ne supprime aucune donnée.
--
-- Seul le serveur (clé secrète / service_role) accède à ces tables. RLS est activé
-- sans aucune politique : les clés publiques (anon, publishable) ne voient rien.

-- Comptes. Le mot de passe est haché côté serveur (format Werkzeug scrypt, compatible ancien site).
create table if not exists public.nathgpt_accounts (
  key             text primary key check (char_length(key) between 3 and 24),
  pseudo          text not null check (char_length(pseudo) between 3 and 24),
  password_hash   text not null,
  tokens_used     bigint not null default 0 check (tokens_used >= 0),
  usage_estimated boolean not null default false,
  created_at      timestamptz not null default now()
);

-- Administrateurs : cocher is_admin (Table Editor > nathgpt_accounts) donne accès à la page Admin.
alter table public.nathgpt_accounts add column if not exists is_admin boolean not null default false;
-- Mode Cricut : cocher cricut donne accès au panneau Cricutastrophe (planche de stickers -> un PNG par sticker).
alter table public.nathgpt_accounts add column if not exists cricut boolean not null default false;

-- Rôles donnés par un admin : tout de suite ou programmés à une date et une heure.
create table if not exists public.nathgpt_role_grants (
  id          bigint generated always as identity primary key,
  account_key text not null references public.nathgpt_accounts(key) on delete cascade,
  role        text not null check (role in ('cricut', 'is_admin')),
  grant_at    timestamptz not null,
  created_by  text,
  created_at  timestamptz not null default now(),
  applied_at  timestamptz,
  seen_at     timestamptz
);
create index if not exists nathgpt_role_grants_due_idx on public.nathgpt_role_grants (applied_at, grant_at);
create index if not exists nathgpt_role_grants_account_idx on public.nathgpt_role_grants (account_key);
alter table public.nathgpt_role_grants enable row level security;
revoke all on public.nathgpt_role_grants from anon, authenticated;
grant select, insert, update, delete on public.nathgpt_role_grants to service_role;

-- Abonnements aux notifications push (une ligne par appareil).
create table if not exists public.nathgpt_push_subscriptions (
  endpoint    text primary key check (endpoint like 'https://%' and char_length(endpoint) <= 1000),
  account_key text not null references public.nathgpt_accounts(key) on delete cascade,
  p256dh      text not null check (char_length(p256dh) <= 200),
  auth        text not null check (char_length(auth) <= 100),
  created_at  timestamptz not null default now()
);
create index if not exists nathgpt_push_account_idx on public.nathgpt_push_subscriptions (account_key);
alter table public.nathgpt_push_subscriptions enable row level security;
revoke all on public.nathgpt_push_subscriptions from anon, authenticated;
grant select, insert, update, delete on public.nathgpt_push_subscriptions to service_role;

-- Sessions : seul le SHA-256 de l'identifiant du cookie est stocké.
create table if not exists public.nathgpt_sessions (
  id_hash     text primary key,
  account_key text not null references public.nathgpt_accounts(key) on delete cascade,
  expires_at  timestamptz not null,
  created_at  timestamptz not null default now()
);
create index if not exists nathgpt_sessions_account_idx on public.nathgpt_sessions (account_key);
create index if not exists nathgpt_sessions_expires_idx on public.nathgpt_sessions (expires_at);

-- Conversations (historique synchronisé entre appareils). Dates en millisecondes, comme le site.
create table if not exists public.nathgpt_conversations (
  id          text primary key check (id ~ '^[A-Za-z0-9_-]{8,128}$'),
  account_key text not null references public.nathgpt_accounts(key) on delete cascade,
  title       text not null default '' check (char_length(title) <= 120),
  messages    jsonb not null default '[]'::jsonb check (jsonb_typeof(messages) = 'array'),
  created_at  bigint not null,
  updated_at  bigint not null
);
create index if not exists nathgpt_conversations_account_idx on public.nathgpt_conversations (account_key, updated_at desc);

alter table public.nathgpt_accounts      enable row level security;
alter table public.nathgpt_sessions      enable row level security;
alter table public.nathgpt_conversations enable row level security;
revoke all on public.nathgpt_accounts, public.nathgpt_sessions, public.nathgpt_conversations from anon, authenticated;

-- Réserve une conversation à un compte ; renvoie false si un autre compte la possède déjà.
create or replace function public.nathgpt_claim_conversation(p_id text, p_account_key text)
returns boolean language plpgsql set search_path = public as $$
declare
  owner text;
  now_ms bigint := (extract(epoch from now()) * 1000)::bigint;
begin
  insert into nathgpt_conversations (id, account_key, created_at, updated_at)
  values (p_id, p_account_key, now_ms, now_ms)
  on conflict (id) do nothing;
  select account_key into owner from nathgpt_conversations where id = p_id;
  return owner = p_account_key;
end $$;

-- Enregistre une conversation, uniquement si elle appartient au compte.
create or replace function public.nathgpt_save_conversation(
  p_id text, p_account_key text, p_title text, p_messages jsonb, p_created_at bigint, p_updated_at bigint)
returns boolean language plpgsql set search_path = public as $$
declare
  changed integer;
begin
  insert into nathgpt_conversations (id, account_key, title, messages, created_at, updated_at)
  values (p_id, p_account_key, left(p_title, 120), p_messages, p_created_at, p_updated_at)
  on conflict (id) do update
    set title = excluded.title, messages = excluded.messages, updated_at = excluded.updated_at
    where nathgpt_conversations.account_key = excluded.account_key;
  get diagnostics changed = row_count;
  return changed > 0;
end $$;

-- Ajoute des tokens au compteur d'économies et renvoie le nouveau total.
create or replace function public.nathgpt_add_usage(p_account_key text, p_tokens bigint, p_estimated boolean)
returns bigint language sql set search_path = public as $$
  update nathgpt_accounts
     set tokens_used = tokens_used + greatest(p_tokens, 0),
         usage_estimated = usage_estimated or p_estimated
   where key = p_account_key
  returning tokens_used;
$$;

-- Nettoyage des sessions expirées (le serveur les supprime aussi à la lecture).
create or replace function public.nathgpt_purge_sessions()
returns integer language sql set search_path = public as $$
  with deleted as (delete from nathgpt_sessions where expires_at <= now() returning 1)
  select count(*)::integer from deleted;
$$;

revoke execute on function public.nathgpt_claim_conversation(text, text) from public, anon, authenticated;
revoke execute on function public.nathgpt_save_conversation(text, text, text, jsonb, bigint, bigint) from public, anon, authenticated;
revoke execute on function public.nathgpt_add_usage(text, bigint, boolean) from public, anon, authenticated;
revoke execute on function public.nathgpt_purge_sessions() from public, anon, authenticated;
grant execute on function public.nathgpt_claim_conversation(text, text) to service_role;
grant execute on function public.nathgpt_save_conversation(text, text, text, jsonb, bigint, bigint) to service_role;
grant execute on function public.nathgpt_add_usage(text, bigint, boolean) to service_role;
grant execute on function public.nathgpt_purge_sessions() to service_role;
grant select, insert, update, delete on public.nathgpt_accounts, public.nathgpt_sessions, public.nathgpt_conversations to service_role;

-- Images générées : bucket Storage PRIVÉ (servi uniquement par le serveur, au propriétaire de l'image).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('nathgpt-images', 'nathgpt-images', false, 20971520, array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;

-- Images de plus d'un jour : le serveur les liste avec cette fonction (toutes les heures),
-- puis les supprime par l'API Storage (Supabase interdit de supprimer des fichiers en SQL).
create or replace function public.nathgpt_expired_images(p_limit integer default 1000)
returns table (name text) language sql stable security definer set search_path = '' as $$
  select o.name from storage.objects o
   where o.bucket_id = 'nathgpt-images' and o.created_at < now() - interval '1 day'
   order by o.created_at
   limit least(greatest(p_limit, 1), 1000);
$$;
revoke execute on function public.nathgpt_expired_images(integer) from public, anon, authenticated;
grant execute on function public.nathgpt_expired_images(integer) to service_role;

-- Facultatif : purge quotidienne avec pg_cron (Database > Extensions > pg_cron), puis :
-- select cron.schedule('nathgpt-purge-sessions', '0 4 * * *', 'select public.nathgpt_purge_sessions()');
