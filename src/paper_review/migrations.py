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
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.exec_driver_sql(stmt)
