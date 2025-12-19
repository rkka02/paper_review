from __future__ import annotations

from sqlalchemy.engine import Engine


def apply_migrations(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    statements = [
        """
        create table if not exists folders (
          id uuid primary key,
          user_id uuid,
          name text not null,
          parent_id uuid references folders(id) on delete cascade,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        """,
        "create index if not exists folders_user_id_idx on folders(user_id);",
        "create index if not exists folders_parent_id_idx on folders(parent_id);",
        "alter table papers add column if not exists folder_id uuid;",
        "create index if not exists ix_papers_folder_id on papers(folder_id);",
        """
        do $$
        begin
          if not exists (
            select 1
            from pg_constraint
            where conname = 'papers_folder_id_fkey'
          ) then
            alter table papers
              add constraint papers_folder_id_fkey
              foreign key (folder_id) references folders(id)
              on delete set null;
          end if;
        end $$;
        """,
        "alter table papers add column if not exists memo text;",
        """
        create table if not exists paper_links (
          id uuid primary key,
          user_id uuid,
          a_paper_id uuid not null references papers(id) on delete cascade,
          b_paper_id uuid not null references papers(id) on delete cascade,
          source text not null default 'user',
          meta jsonb,
          created_at timestamptz not null default now()
        );
        """,
        "alter table paper_links add column if not exists meta jsonb;",
        "create index if not exists paper_links_user_id_idx on paper_links(user_id);",
        "create index if not exists paper_links_a_idx on paper_links(a_paper_id);",
        "create index if not exists paper_links_b_idx on paper_links(b_paper_id);",
        "create index if not exists paper_links_source_idx on paper_links(source);",
        "create unique index if not exists paper_links_pair_uniq on paper_links(a_paper_id, b_paper_id);",
        """
        do $$
        begin
          if not exists (
            select 1
            from pg_constraint
            where conname = 'paper_links_no_self'
          ) then
            alter table paper_links
              add constraint paper_links_no_self
              check (a_paper_id <> b_paper_id);
          end if;
        end $$;
        """,
        """
        create table if not exists paper_embeddings (
          paper_id uuid primary key references papers(id) on delete cascade,
          provider text not null,
          model text not null,
          dim int not null,
          vector jsonb not null,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        """,
        "alter table paper_embeddings add column if not exists provider text;",
        "alter table paper_embeddings add column if not exists model text;",
        "alter table paper_embeddings add column if not exists dim int;",
        "alter table paper_embeddings add column if not exists vector jsonb;",
        "alter table paper_embeddings add column if not exists created_at timestamptz;",
        "alter table paper_embeddings add column if not exists updated_at timestamptz;",
        "create index if not exists paper_embeddings_provider_idx on paper_embeddings(provider);",
        """
        create table if not exists recommendation_runs (
          id uuid primary key,
          source text not null default 'local',
          meta jsonb,
          created_at timestamptz not null default now()
        );
        """,
        "alter table recommendation_runs add column if not exists source text;",
        "alter table recommendation_runs add column if not exists meta jsonb;",
        "alter table recommendation_runs add column if not exists created_at timestamptz;",
        "create index if not exists recommendation_runs_source_idx on recommendation_runs(source);",
        "create index if not exists recommendation_runs_created_at_idx on recommendation_runs(created_at);",
        """
        create table if not exists recommendation_items (
          id uuid primary key,
          run_id uuid not null references recommendation_runs(id) on delete cascade,
          kind text not null,
          folder_id uuid references folders(id) on delete set null,
          rank int not null,
          semantic_scholar_paper_id text,
          title text not null,
          doi text,
          url text,
          year int,
          venue text,
          authors jsonb,
          abstract text,
          score double precision,
          one_liner text,
          summary text,
          rationale jsonb,
          created_at timestamptz not null default now()
        );
        """,
        "alter table recommendation_items add column if not exists run_id uuid;",
        "alter table recommendation_items add column if not exists kind text;",
        "alter table recommendation_items add column if not exists folder_id uuid;",
        "alter table recommendation_items add column if not exists rank int;",
        "alter table recommendation_items add column if not exists semantic_scholar_paper_id text;",
        "alter table recommendation_items add column if not exists title text;",
        "alter table recommendation_items add column if not exists doi text;",
        "alter table recommendation_items add column if not exists url text;",
        "alter table recommendation_items add column if not exists year int;",
        "alter table recommendation_items add column if not exists venue text;",
        "alter table recommendation_items add column if not exists authors jsonb;",
        "alter table recommendation_items add column if not exists abstract text;",
        "alter table recommendation_items add column if not exists score double precision;",
        "alter table recommendation_items add column if not exists one_liner text;",
        "alter table recommendation_items add column if not exists summary text;",
        "alter table recommendation_items add column if not exists rationale jsonb;",
        "alter table recommendation_items add column if not exists created_at timestamptz;",
        "create index if not exists recommendation_items_run_id_idx on recommendation_items(run_id);",
        "create index if not exists recommendation_items_folder_id_idx on recommendation_items(folder_id);",
        "create index if not exists recommendation_items_kind_idx on recommendation_items(kind);",
        "create unique index if not exists recommendation_items_run_group_rank_uniq "
        "on recommendation_items(run_id, kind, folder_id, rank);",
        """
        create table if not exists recommendation_tasks (
          id uuid primary key,
          trigger text not null default 'manual',
          status text not null default 'queued',
          config jsonb,
          logs jsonb,
          run_id uuid references recommendation_runs(id) on delete set null,
          error text,
          created_at timestamptz not null default now(),
          started_at timestamptz,
          finished_at timestamptz
        );
        """,
        "alter table recommendation_tasks add column if not exists trigger text;",
        "alter table recommendation_tasks add column if not exists status text;",
        "alter table recommendation_tasks add column if not exists config jsonb;",
        "alter table recommendation_tasks add column if not exists logs jsonb;",
        "alter table recommendation_tasks add column if not exists run_id uuid;",
        "alter table recommendation_tasks add column if not exists error text;",
        "alter table recommendation_tasks add column if not exists created_at timestamptz;",
        "alter table recommendation_tasks add column if not exists started_at timestamptz;",
        "alter table recommendation_tasks add column if not exists finished_at timestamptz;",
        "create index if not exists recommendation_tasks_status_idx on recommendation_tasks(status);",
        "create index if not exists recommendation_tasks_trigger_idx on recommendation_tasks(trigger);",
        "create index if not exists recommendation_tasks_created_at_idx on recommendation_tasks(created_at);",
        """
        create table if not exists recommendation_excludes (
          id uuid primary key,
          doi_norm text,
          arxiv_id text,
          semantic_scholar_paper_id text,
          title text,
          title_norm text not null,
          reason text,
          source_item_id uuid references recommendation_items(id) on delete set null,
          created_at timestamptz not null default now()
        );
        """,
        "alter table recommendation_excludes add column if not exists doi_norm text;",
        "alter table recommendation_excludes add column if not exists arxiv_id text;",
        "alter table recommendation_excludes add column if not exists semantic_scholar_paper_id text;",
        "alter table recommendation_excludes add column if not exists title text;",
        "alter table recommendation_excludes add column if not exists title_norm text;",
        "alter table recommendation_excludes add column if not exists reason text;",
        "alter table recommendation_excludes add column if not exists source_item_id uuid;",
        "alter table recommendation_excludes add column if not exists created_at timestamptz;",
        "create index if not exists recommendation_excludes_title_norm_idx on recommendation_excludes(title_norm);",
        "create index if not exists recommendation_excludes_source_item_idx on recommendation_excludes(source_item_id);",
        "create unique index if not exists recommendation_excludes_doi_uniq on recommendation_excludes(doi_norm) where doi_norm is not null;",
        "create unique index if not exists recommendation_excludes_arxiv_uniq on recommendation_excludes(arxiv_id) where arxiv_id is not null;",
        "create unique index if not exists recommendation_excludes_s2_uniq "
        "on recommendation_excludes(semantic_scholar_paper_id) where semantic_scholar_paper_id is not null;",
        """
        create table if not exists discord_debate_threads (
          id uuid primary key,
          discord_thread_id bigint not null,
          discord_channel_id bigint not null,
          discord_guild_id bigint,
          created_by_user_id bigint,
          topic text not null,
          is_active boolean not null default false,
          session_started_at timestamptz not null default now(),
          persona_a_key text not null default 'hikari',
          persona_b_key text not null default 'rei',
          moderator_key text not null default 'tsugumi',
          next_duo_speaker_key text not null default 'hikari',
          next_speaker_key text not null default 'hikari',
          duo_turns_since_moderation int not null default 0,
          turn_count int not null default 0,
          max_turns int not null default 200,
          last_turn_at timestamptz,
          next_turn_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        """,
        "alter table discord_debate_threads add column if not exists session_started_at timestamptz not null default now();",
        "create unique index if not exists discord_debate_threads_thread_uniq on discord_debate_threads(discord_thread_id);",
        "create index if not exists discord_debate_threads_active_idx on discord_debate_threads(is_active);",
        "create index if not exists discord_debate_threads_next_turn_idx on discord_debate_threads(next_turn_at);",
        "create index if not exists discord_debate_threads_guild_idx on discord_debate_threads(discord_guild_id);",
        "create index if not exists discord_debate_threads_channel_idx on discord_debate_threads(discord_channel_id);",
        "create index if not exists discord_debate_threads_created_by_idx on discord_debate_threads(created_by_user_id);",
        """
        create table if not exists discord_debate_turns (
          id uuid primary key,
          thread_id uuid not null references discord_debate_threads(id) on delete cascade,
          speaker_key text not null,
          source text not null default 'agent',
          content text not null,
          discord_message_id bigint,
          meta jsonb,
          created_at timestamptz not null default now()
        );
        """,
        "create index if not exists discord_debate_turns_thread_idx on discord_debate_turns(thread_id);",
        "create index if not exists discord_debate_turns_speaker_idx on discord_debate_turns(speaker_key);",
        "create index if not exists discord_debate_turns_source_idx on discord_debate_turns(source);",
        "create index if not exists discord_debate_turns_created_at_idx on discord_debate_turns(created_at);",
    ]

    # Autocommit DDL and serialize with an advisory lock to reduce deadlocks.
    lock_key = 732104
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"select pg_advisory_lock({lock_key});")
        try:
            for stmt in statements:
                conn.exec_driver_sql(stmt)
        finally:
            conn.exec_driver_sql(f"select pg_advisory_unlock({lock_key});")
