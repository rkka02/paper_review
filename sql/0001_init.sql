-- Minimal schema based on `main.txt` (MVP).

create table if not exists folders (
  id uuid primary key,
  user_id uuid,
  name text not null,
  parent_id uuid references folders(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists folders_user_id_idx on folders(user_id);
create index if not exists folders_parent_id_idx on folders(parent_id);

create table if not exists papers (
  id uuid primary key,
  user_id uuid,
  folder_id uuid references folders(id) on delete set null,
  title text,
  doi text,
  drive_file_id text not null,
  pdf_sha256 text,
  pdf_size_bytes bigint,
  abstract text,
  status text not null default 'to_read' check (status in ('to_read','reading','done')),
  memo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists papers_user_id_idx on papers(user_id);
create index if not exists papers_doi_idx on papers(doi);
create index if not exists papers_status_idx on papers(status);

alter table papers add column if not exists folder_id uuid;
alter table papers add column if not exists memo text;

create index if not exists papers_folder_id_idx on papers(folder_id);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'papers_folder_id_fkey') then
    alter table papers
      add constraint papers_folder_id_fkey
      foreign key (folder_id) references folders(id)
      on delete set null;
  end if;
end $$;

create table if not exists paper_metadata (
  paper_id uuid primary key references papers(id) on delete cascade,
  authors jsonb,
  year int,
  venue text,
  url text,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists analysis_runs (
  id uuid primary key,
  paper_id uuid not null references papers(id) on delete cascade,
  stage text not null default 'single_session_review',
  openai_file_id text,
  status text not null default 'queued' check (status in ('queued','running','succeeded','failed')),
  error text,
  timings jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists analysis_runs_paper_id_idx on analysis_runs(paper_id);
create index if not exists analysis_runs_status_idx on analysis_runs(status);

create table if not exists analysis_outputs (
  id uuid primary key,
  analysis_run_id uuid not null references analysis_runs(id) on delete cascade,
  canonical_json jsonb not null,
  content_md text,
  created_at timestamptz not null default now()
);

create index if not exists analysis_outputs_run_id_idx on analysis_outputs(analysis_run_id);

create table if not exists evidence_snippets (
  id uuid primary key,
  paper_id uuid not null references papers(id) on delete cascade,
  analysis_run_id uuid references analysis_runs(id) on delete cascade,
  page int,
  quote text,
  why text,
  source text check (source in ('normalization','persona')),
  created_at timestamptz not null default now()
);

create index if not exists evidence_snippets_paper_id_idx on evidence_snippets(paper_id);

create table if not exists reviews (
  id uuid primary key,
  paper_id uuid not null unique references papers(id) on delete cascade,
  one_liner text,
  summary text,
  pros text,
  cons text,
  rating_overall int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists paper_links (
  id uuid primary key,
  user_id uuid,
  a_paper_id uuid not null references papers(id) on delete cascade,
  b_paper_id uuid not null references papers(id) on delete cascade,
  source text not null default 'user',
  meta jsonb,
  created_at timestamptz not null default now(),
  constraint paper_links_no_self check (a_paper_id <> b_paper_id),
  constraint paper_links_pair_uniq unique (a_paper_id, b_paper_id)
);

alter table paper_links add column if not exists meta jsonb;

create index if not exists paper_links_user_id_idx on paper_links(user_id);
create index if not exists paper_links_a_idx on paper_links(a_paper_id);
create index if not exists paper_links_b_idx on paper_links(b_paper_id);
create index if not exists paper_links_source_idx on paper_links(source);
create unique index if not exists paper_links_pair_uniq on paper_links(a_paper_id, b_paper_id);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'paper_links_no_self') then
    alter table paper_links
      add constraint paper_links_no_self
      check (a_paper_id <> b_paper_id);
  end if;
end $$;

create table if not exists paper_embeddings (
  paper_id uuid primary key references papers(id) on delete cascade,
  provider text not null,
  model text not null,
  dim int not null,
  vector jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists paper_embeddings_provider_idx on paper_embeddings(provider);

create table if not exists recommendation_runs (
  id uuid primary key,
  source text not null default 'local',
  meta jsonb,
  created_at timestamptz not null default now()
);

create index if not exists recommendation_runs_source_idx on recommendation_runs(source);
create index if not exists recommendation_runs_created_at_idx on recommendation_runs(created_at);

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

create index if not exists recommendation_items_run_id_idx on recommendation_items(run_id);
create index if not exists recommendation_items_folder_id_idx on recommendation_items(folder_id);
create index if not exists recommendation_items_kind_idx on recommendation_items(kind);
create unique index if not exists recommendation_items_run_group_rank_uniq
  on recommendation_items(run_id, kind, folder_id, rank);
