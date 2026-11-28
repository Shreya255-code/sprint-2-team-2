-- Stores Team 2's divided per-case matching and document-verification output.
-- This project has no claims_cases table, so keep these results in a dedicated table.
CREATE TABLE IF NOT EXISTS public.package_matching_records (
    case_number TEXT PRIMARY KEY,
    matching_output JSONB NOT NULL CHECK (jsonb_typeof(matching_output) = 'object'),
    source_file TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.package_matching_records ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.package_matching_records IS
    'Per-case Sprint 2 Team 2 package matching and document verification output';
