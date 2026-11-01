-- ForestSentinel database schema for Supabase (Postgres).
-- Replaces the six Firestore collections used by the ETL, analysis and
-- conservation pipelines. Safe to run more than once.

-- ---------------------------------------------------------------------------
-- Part 1: ETL
-- ---------------------------------------------------------------------------

-- One row per validated NASA FIRMS detection; the SHA-256 detection_key makes
-- re-running the ETL idempotent (existing keys are skipped, not duplicated).
create table if not exists public.fire_detections (
    detection_key      text primary key,
    latitude           double precision not null,
    longitude          double precision not null,
    acq_datetime       timestamptz not null,
    acq_date           text not null,
    acq_time           text not null,
    satellite          text,
    instrument         text,
    confidence         text,
    frp                double precision,
    bright_ti4         double precision,
    bright_ti5         double precision,
    daynight           text,
    source_row_number  integer not null,
    ingested_at        timestamptz not null default now(),
    etl_run_id         text
);
-- Part 2 reads detections inside a recent time window.
create index if not exists fire_detections_acq_datetime_idx
    on public.fire_detections (acq_datetime desc);

-- Records that failed cleaning or Pydantic validation, kept for auditing.
create table if not exists public.rejected_records (
    id                 bigint generated always as identity primary key,
    etl_run_id         text not null,
    source_row_number  integer not null default 0,
    raw_record         jsonb not null default '{}'::jsonb,
    rejection_reason   text not null,
    rejected_at        timestamptz not null default now()
);
create index if not exists rejected_records_run_idx on public.rejected_records (etl_run_id);

create table if not exists public.etl_runs (
    run_id                    text primary key,
    started_at                timestamptz not null default now(),
    finished_at               timestamptz,
    status                    text not null default 'running',
    api_source                text,
    study_bbox                text,
    day_range                 integer default 0,
    raw_rows_extracted        integer default 0,
    exact_duplicates_removed  integer default 0,
    cleaning_rejections       integer default 0,
    pydantic_rejections       integer default 0,
    valid_records             integer default 0,
    inserted_records          integer default 0,
    skipped_existing_records  integer default 0,
    error_message             text
);

-- ---------------------------------------------------------------------------
-- Part 3: Conservation (GBIF / IUCN)
-- ---------------------------------------------------------------------------

create table if not exists public.conservation_analysis_runs (
    run_id                                  text primary key,
    started_at                              timestamptz not null default now(),
    finished_at                             timestamptz,
    status                                  text not null default 'running',
    source_fire_analysis_run                text,
    grid_size_degrees                       double precision default 0.25,
    priority_cells_considered               integer default 0,
    gbif_requests_made                      integer default 0,
    gbif_occurrence_records_received        integer default 0,
    unique_animal_species_found             integer default 0,
    species_with_verified_iucn_status       integer default 0,
    threatened_species_found                integer default 0,
    aggregated_grid_species_records_saved   integer default 0,
    error_message                           text
);

-- Species aggregated to 0.25° grid cells. Exact wildlife coordinates are
-- never stored; the full summary record lives in "data".
create table if not exists public.species_grid_summaries (
    id               text primary key,          -- "<grid_id>_<taxon_key or name>"
    run_id           text,
    grid_id          text not null,
    taxon_key        bigint,
    scientific_name  text,
    data             jsonb not null default '{}'::jsonb,
    saved_at         timestamptz not null default now()
);
create index if not exists species_grid_summaries_grid_idx on public.species_grid_summaries (grid_id);

-- Cache of IUCN Red List lookups so a species is only verified once.
create table if not exists public.conservation_assessments (
    id                    text primary key,     -- "taxon_<key>" or "sci_<name>"
    taxon_key             bigint,
    scientific_name       text not null,
    iucn_category         text,
    iucn_assessment_date  text,
    iucn_verified         boolean not null default false,
    iucn_source           text default 'iucn_api_v4',
    retrieved_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Security: row-level security on, no public policies. Only the pipeline's
-- service_role key (which bypasses RLS) can read or write these tables.
-- ---------------------------------------------------------------------------
alter table public.fire_detections            enable row level security;
alter table public.rejected_records           enable row level security;
alter table public.etl_runs                   enable row level security;
alter table public.conservation_analysis_runs enable row level security;
alter table public.species_grid_summaries     enable row level security;
alter table public.conservation_assessments   enable row level security;
