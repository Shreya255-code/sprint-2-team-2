-- Stores the structured Sprint 2 Team 2 matching and document-verification output.
-- Safe to apply more than once.
ALTER TABLE public.claims_cases
    ADD COLUMN IF NOT EXISTS package_matching_results JSONB;

COMMENT ON COLUMN public.claims_cases.package_matching_results IS
    'Structured package matching and document verification output from Sprint 2 Team 2';
