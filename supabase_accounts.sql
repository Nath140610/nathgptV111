-- À exécuter une seule fois dans Supabase : SQL Editor > New query.
-- Les mots de passe restent hachés dans la colonne JSONB : ils ne sont jamais
-- envoyés au navigateur.

create table if not exists public.nathgpt_accounts (
    username text primary key check (char_length(username) between 1 and 80),
    data jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create or replace function public.nathgpt_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists nathgpt_accounts_updated_at on public.nathgpt_accounts;
create trigger nathgpt_accounts_updated_at
before update on public.nathgpt_accounts
for each row execute function public.nathgpt_set_updated_at();

-- Aucune donnée n'est accessible depuis le navigateur. Seul le serveur
-- Render utilisant la clé secrète Supabase peut lire et écrire la table.
alter table public.nathgpt_accounts enable row level security;
revoke all on table public.nathgpt_accounts from anon, authenticated;
grant select, insert, update, delete on table public.nathgpt_accounts to service_role;


-- Historique NathGPT persistant sur Supabase.
-- Une ligne par utilisateur, avec ses conversations dans un tableau JSONB.
create table if not exists public.nathgpt_conversations (
    username text primary key check (char_length(username) between 1 and 80),
    data jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

drop trigger if exists nathgpt_conversations_updated_at on public.nathgpt_conversations;
create trigger nathgpt_conversations_updated_at
before update on public.nathgpt_conversations
for each row execute function public.nathgpt_set_updated_at();

alter table public.nathgpt_conversations enable row level security;
revoke all on table public.nathgpt_conversations from anon, authenticated;
grant select, insert, update, delete on table public.nathgpt_conversations to service_role;

-- Signalements de bugs envoyés depuis l'interface NathGPT.
create table if not exists public.nathgpt_bug_reports (
    id text primary key,
    username text not null,
    category text not null default 'Autre',
    description text not null,
    conversation_id text,
    device text,
    created_at timestamptz not null default now(),
    status text not null default 'new'
);
alter table public.nathgpt_bug_reports enable row level security;
revoke all on table public.nathgpt_bug_reports from anon, authenticated;
grant select, insert, update, delete on table public.nathgpt_bug_reports to service_role;



-- Etat persistant de l'application : maintenance manuelle et programmée.
create table if not exists public.nathgpt_app_state (
    key text primary key,
    data jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);
drop trigger if exists nathgpt_app_state_updated_at on public.nathgpt_app_state;
create trigger nathgpt_app_state_updated_at
before update on public.nathgpt_app_state
for each row execute function public.nathgpt_set_updated_at();
alter table public.nathgpt_app_state enable row level security;
revoke all on table public.nathgpt_app_state from anon, authenticated;
grant select, insert, update, delete on table public.nathgpt_app_state to service_role;
