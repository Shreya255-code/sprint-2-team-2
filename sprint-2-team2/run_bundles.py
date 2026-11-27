"""Package matching on Sprint 1 output files (Squad 3 combined bundle, one <case_number>.json each).
   python run_bundles.py <bundle_dir> <patients_dir> <output.json>
The bundles carry no document text, so text is read from the original documents in <patients_dir>
(needs pdftotext and tesseract; no PII masking, so synthetic data only)."""
import json
import re
import sys
from pathlib import Path

from pkg_engine.adapters import build_case
from pkg_engine.catalog import Catalog
from pkg_engine.engine import evaluate
from pkg_engine.report import to_output, to_table
from run_folder import KINDS, read


def key(name):
    """'P03_Lab_Report_1_.png' and 'P03_Lab_Report.png' are the same document."""
    return re.sub(r"(_\d+_)(?=\.\w+$)", "", name).lower()


def main(bundle_dir, patients_dir, output_file):
    files = {}
    for path in Path(patients_dir).rglob("*"):
        if path.suffix.lower() in KINDS:
            if key(path.name) in files:
                sys.exit(f"Two files named {path.name}: cannot tell which belongs to the case")
            files[key(path.name)] = path
    cat, outputs = Catalog(), []
    for bundle_path in sorted(Path(bundle_dir).glob("*.json")):
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        names = [d["file_name"] for d in bundle["documents"]]
        absent = [n for n in names if key(n) not in files]
        if absent:
            sys.exit(f"{bundle['case_number']}: original document(s) not found: {', '.join(absent)}")
        docs = [(n, read(files[key(n)])) for n in names]
        result = evaluate(cat, build_case(bundle["case_number"], docs, bundle))
        outputs.append(to_output(result))
        print(f"\n{to_table(outputs[-1])}\n flags: {result['review_flags']}")
    Path(output_file).write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
