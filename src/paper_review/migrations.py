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
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.exec_driver_sql(stmt)
