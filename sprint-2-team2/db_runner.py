"""Sprint 2 Team 2 <-> Supabase. Reads cases Sprint 1 finished (pipeline_stage = COMPLETED).
   python db_runner.py [CASE ...] [--dry-run] [--force]
Writes package_code, primary_diagnosis, requested_procedure, missing_mandatory_docs and
case_audit_summary.sprint2_team2. pipeline_stage, case_status and admissibility_score are not touched."""
import os
import sys

from pkg_engine.adapters import build_case
from pkg_engine.catalog import Catalog
from pkg_engine.engine import ENGINE_VERSION, evaluate, rfi_draft
from pkg_engine.report import to_output, to_table

KEY = "sprint2_team2"


def connect():
    from supabase import create_client
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (service_role key) first.")
    return create_client(url, key)


def updates_for(case_row, result):
    """Columns to write. A value someone else set is never overwritten."""
    audit = dict(case_row.get("case_audit_summary") or {})
    ours = (audit.get(KEY) or {}).get("written_columns", {})
    selected = result["selected_package"]
    wanted = {
        "package_code": selected["package_code"] if selected else None,
        "primary_diagnosis": result["diagnoses"][0][:255] if result["diagnoses"] else None,
        "requested_procedure": result["procedures"][0][:255] if result["procedures"] else None,
    }
    update, written = {}, {}
    for col, value in wanted.items():
        current = case_row.get(col)
        if current and current != ours.get(col):
            if value and current != value:
                result["review_flags"].append(f"{col} already '{current}', engine found '{value}': left unchanged")
            continue
        if value != current:
            update[col] = value
        written[col] = value
    if result["document_status"] != "NOT_CHECKED":
        update["missing_mandatory_docs"] = result["missing_mandatory_docs"]
    else:
        update["missing_mandatory_docs"] = []
    audit[KEY] = {**result, "output": to_output(result, case_row.get("case_id")), "written_columns": written}
    update["case_audit_summary"] = audit
    return update


def run(sb, cat, case_numbers=None, dry=False, force=False):
    rows = (sb.table("claims_cases")
            .select("case_id, case_number, package_code, primary_diagnosis, requested_procedure, "
                    "case_audit_summary, master_fhir_bundle_json")
            .eq("pipeline_stage", "COMPLETED").execute().data or [])
    done = 0
    for row in rows:
        cn = row["case_number"]
        if case_numbers and cn not in case_numbers:
            continue
        previous = (row.get("case_audit_summary") or {}).get(KEY) or {}
        if previous.get("engine_version") == ENGINE_VERSION and not force:
            continue
        if not row.get("master_fhir_bundle_json"):
            print(f"{cn}: no Squad 3 bundle, skipped")
            continue
        try:
            docs = (sb.table("claim_documents").select("file_name, redacted_ocr_json")
                    .eq("case_id", row["case_id"]).execute().data or [])
            texts = []
            for d in docs:
                red = d.get("redacted_ocr_json") or {}
                text = red.get("masked_text") or "\n".join(p.get("masked_text") or "" for p in red.get("pages") or [])
                texts.append((d["file_name"], text))
            result = evaluate(cat, build_case(cn, texts, row["master_fhir_bundle_json"]))
            result["rfi_draft"] = rfi_draft(result)
            update = updates_for(row, result)
            if not dry:
                sb.table("claims_cases").update(update).eq("case_id", row["case_id"]).execute()
            done += 1
            print(f"{cn}: {result['match_status']}, {result['document_status']}, "
                  f"missing {len(result['missing_mandatory_docs'])}" + (" (dry run)" if dry else ""))
            print(to_table(update["case_audit_summary"][KEY]["output"]))
        except Exception as error:                      # one bad case must not stop the rest
            print(f"{cn}: FAILED - {error}", file=sys.stderr)
    print(f"{done} case(s) evaluated")
    return done


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(connect(), Catalog(), args or None, "--dry-run" in sys.argv, "--force" in sys.argv)
