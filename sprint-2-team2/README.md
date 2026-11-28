# Sprint 2, Team 2: Package Matching & Document Verification Engine

```
Sprint 1 (masked text + master_fhir_bundle_json) -> this engine <- Team 1 (nha_packages.sqlite3)
                                                       |
             package code, confidence, checklist, missing documents, RFI draft
```

## Run
```bash
python match_case.py          # offline; prints tables, writes outputs/<case>.json (+ .details.json)
python -m pytest -q           # tests

pip install -r requirements.txt
export SUPABASE_URL=... SUPABASE_SERVICE_KEY=...
python db_runner.py --dry-run # evaluate completed Sprint 1 cases, write nothing
python db_runner.py           # write results (--force re-evaluates)
python run_all.py             # Squad 2 + 3 through orchestrator/, then this engine
```
`run_all.py` also needs the Sprint 1 requirements and `GEMINI_API_KEY`.
`match_case.py` reads the `Diagnosis:` / `Procedure:` labels instead of calling Gemini, so it does
not test Squad 3's extraction.

## Output format
`case_id`, `case_number`, `medication_number` (MRN), `diagnosis`, `procedure`, `hospital_name`, `package_match`, `completeness.requirements[]` (see `pkg_engine/report.py`).
The divided sample files are stored in `package_matching_records.matching_output`.

`python run_bundles.py <bundle_dir> <patients_dir> <output_dir>` runs on Sprint 1 output files and writes one JSON per patient.

## Database
The Supabase project currently has the NHA `investigation_review_queue` table but no
`claims_cases` or `claim_documents` tables. Team 2's divided output therefore uses a
separate `package_matching_records` table. Apply
`supabase/migrations/20261128_add_package_matching_results.sql` in the Supabase SQL Editor
before importing the sample output. The table has a unique `case_number`, stores each full
JSON object in `matching_output`, and has row-level security enabled.

`db_runner.py` is an optional adapter for deployments that separately provide the Sprint 1
`claims_cases` and `claim_documents` schema; it writes to `case_audit_summary.sprint2_team2`.

To load the per-case JSON files in `sample_output/`, set `SUPABASE_URL` and
`SUPABASE_SERVICE_KEY`, then run `python import_sample_output.py` for a preview or
`python import_sample_output.py --apply` to write the files. The importer matches by
`case_number` and skips rows already present; use `--apply --force` only to replace them.

## How matching works
1. Normalize: abbreviations, OCR slips, anaesthesia wording, laterality (`config/terminology.json`).
2. Tests reported as procedures (X-ray, CBC) are set aside.
3. Score every NHA procedure: rarity-weighted word overlap, diagnosis support; penalties for
   contradictions (lap/open), undocumented qualifiers and child packages for adults.
4. A package code written in the record is accepted only if the description agrees (then `MATCHED`);
   otherwise the case goes to review.
5. `MATCHED` (>= 0.75 and clear lead), `AMBIGUOUS` (top two within 0.10), `NEEDS_REVIEW`, `NO_MATCH`.
   A package is selected only when `MATCHED`.

The score is a hand-tuned text-agreement score, not a probability. Thresholds have not been
calibrated against labelled claims.

## Requirements and their reliability (`config/requirements.json`)
| verification | meaning | counted as missing? |
|---|---|---|
| `NHA` | NHA publication | yes |
| `STATE_ADVISORY` | one state-level advisory (appears to be Haryana) | yes |
| `PROVISIONAL` | team assumption | no, "recommended" only |
| `TEAM1_DB` | mandatory rows Team 1 adds later | shown for manual check |

The package-specific Standard Treatment Guideline for cataract was **not** obtained, and Team 1's
database holds no document or investigation requirements. So the best document status is
`KNOWN_REQUIREMENTS_MET`, never "complete". Confirm `config/requirements.json` against the STGs in
your state's TMS before real use. HBP 2.2 is cited for rules while Team 1's catalogue is HBP 2022.

## Limits
- Package-specific rules exist only for a few packages (mainly SE020); others get the general ones.
- Photos and IOL stickers are recognised by file name only (e.g. `iol_sticker.jpg`, `photo_before.jpg`).
- Evaluated on 5 synthetic cataract patients plus unit tests; no accuracy figure can be claimed.
