"""Import per-case output into claims_cases.case_audit_summary.sprint2_team2.output.

Preview without writes:
    python import_sample_output.py

Write rows that are not already present:
    python import_sample_output.py --apply

Replace existing Team 2 output values as well:
    python import_sample_output.py --apply --force
"""
import argparse
import json
import sys
from pathlib import Path

from db_runner import connect


OUTPUT_DIR = Path(__file__).parent / "sample_output"


def load_outputs(directory=OUTPUT_DIR):
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"No per-case JSON files found in {directory}")

    outputs = []
    seen = set()
    for path in files:
        with path.open(encoding="utf-8") as stream:
            item = json.load(stream)
        if not isinstance(item, dict) or not item.get("case_number"):
            raise ValueError(f"{path}: expected a JSON object with case_number")
        match = item.get("package_match")
        if not isinstance(match, dict) or not {"confidence_score", "candidates", "review_flags"}.issubset(match):
            raise ValueError(f"{path}: regenerate output with confidence_score, candidates, and review_flags")
        case_number = item["case_number"]
        if case_number in seen:
            raise ValueError(f"Duplicate case_number {case_number!r} in sample_output")
        seen.add(case_number)
        outputs.append((path, item))
    return outputs


def import_outputs(sb, outputs, apply=False, force=False):
    case_numbers = [item["case_number"] for _, item in outputs]
    rows = (sb.table("claims_cases")
            .select("case_id, case_number, case_audit_summary")
            .in_("case_number", case_numbers).execute().data or [])
    cases = {row["case_number"]: row for row in rows}
    missing = sorted(set(case_numbers) - set(cases))
    if missing:
        raise ValueError("No claims_cases row found for: " + ", ".join(missing))

    saved = 0
    for path, item in outputs:
        number = item["case_number"]
        case = cases[number]
        summary = case.get("case_audit_summary") or {}
        if not isinstance(summary, dict):
            raise ValueError(f"{number}: case_audit_summary is not a JSON object")
        team2 = summary.get("sprint2_team2") or {}
        if not isinstance(team2, dict):
            raise ValueError(f"{number}: case_audit_summary.sprint2_team2 is not a JSON object")
        if team2.get("output") is not None and not force:
            print(f"{number}: Team 2 output already exists; skipped (use --force to replace)")
            continue

        updated_team2 = dict(team2)
        updated_team2["output"] = item
        updated_summary = dict(summary)
        updated_summary["sprint2_team2"] = updated_team2
        if apply:
            (sb.table("claims_cases").update({"case_audit_summary": updated_summary})
             .eq("case_id", case["case_id"]).execute())
        saved += 1
        print(f"{number}: {'saved' if apply else 'ready to save'} from {path.name}")
    print(f"{saved} output(s) {'written' if apply else 'ready (dry run; no database changes)'}")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes to Supabase; default is preview only")
    parser.add_argument("--force", action="store_true", help="replace existing package_matching_results")
    args = parser.parse_args()
    if args.force and not args.apply:
        parser.error("--force requires --apply")
    try:
        import_outputs(connect(), load_outputs(), apply=args.apply, force=args.force)
    except Exception as error:
        sys.exit(f"Import failed: {error}")
