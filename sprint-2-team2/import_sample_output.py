"""Import the per-case JSON files in sample_output into Supabase.

Preview without writes:
    python import_sample_output.py

Write rows that are not already present:
    python import_sample_output.py --apply

Replace existing values as well:
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
        case_number = item["case_number"]
        if case_number in seen:
            raise ValueError(f"Duplicate case_number {case_number!r} in sample_output")
        seen.add(case_number)
        outputs.append((path, item))
    return outputs


def import_outputs(sb, outputs, apply=False, force=False):
    rows = (sb.table("package_matching_records")
            .select("case_number").execute().data or [])
    existing = {row["case_number"] for row in rows}

    saved = 0
    for path, item in outputs:
        number = item["case_number"]
        if number in existing and not force:
            print(f"{number}: already exists; skipped (use --force to replace)")
            continue

        payload = {
            "case_number": number,
            "matching_output": item,
            "source_file": path.name,
        }
        if apply:
            if number in existing:
                sb.table("package_matching_records").upsert(payload, on_conflict="case_number").execute()
            else:
                sb.table("package_matching_records").insert(payload).execute()
                existing.add(number)
        saved += 1
        print(f"{number}: {'saved' if apply else 'ready to save'} from {path.name}")
    print(f"{saved} output(s) {'written' if apply else 'matched (dry run; no database changes)'}")
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
