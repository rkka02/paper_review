-- Minimal schema based on `main.txt` (MVP).

create table if not exists papers (
  id uuid primary key,
  user_id uuid,
  title text,
  doi text,
  drive_file_id text not null,
  pdf_sha256 text,
  pdf_size_bytes bigint,
  abstract text,
  status text not null default 'to_read' check (status in ('to_read','reading','done')),
  tags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists papers_user_id_idx on papers(user_id);
create index if not exists papers_doi_idx on papers(doi);
create index if not exists papers_status_idx on papers(status);

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

