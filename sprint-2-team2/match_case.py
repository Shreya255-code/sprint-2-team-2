"""Offline run on Squad 2's sample output (no Supabase / Gemini needed).
   python match_case.py [masked_output.json]"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from pkg_engine.adapters import build_case, bundle_from_labels
from pkg_engine.catalog import Catalog
from pkg_engine.engine import evaluate, rfi_draft
from pkg_engine.report import to_output, to_table

HERE = Path(__file__).parent
SAMPLE = HERE.parent / "squad2_pii" / "samples" / "masked_output.json"


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data["documents"]
    cases = defaultdict(list)
    for r in rows:
        cases[r["case_id"]].append((r["doc_id"], r.get("masked_text", "")))
    return [build_case(cn, docs, bundle_from_labels(docs)) for cn, docs in sorted(cases.items())]


def main():
    cat = Catalog()
    out = HERE / "outputs"
    out.mkdir(exist_ok=True)
    for case in load(sys.argv[1] if len(sys.argv) > 1 else SAMPLE):
        r = evaluate(cat, case)
        r["rfi_draft"] = rfi_draft(r)
        output = to_output(r)
        (out / f"{r['case_number']}.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
        (out / f"{r['case_number']}.details.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
        print(f"\n{to_table(output)}")


if __name__ == "__main__":
    main()
