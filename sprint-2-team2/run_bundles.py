"""Package matching on Sprint 1 output files (Squad 3 combined bundle, one <case_number>.json each).
   python run_bundles.py <bundle_dir> <patients_dir> <output_dir>
Writes one <case_number>.json per patient into <output_dir>.
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


def main(bundle_dir, patients_dir, output_dir):
    files = {}
    for path in Path(patients_dir).rglob("*"):
        if path.suffix.lower() in KINDS:
            if key(path.name) in files:
                sys.exit(f"Two files named {path.name}: cannot tell which belongs to the case")
            files[key(path.name)] = path
    cat, out = Catalog(), Path(output_dir)
    if out.resolve() == Path(bundle_dir).resolve():
        sys.exit("Output folder must differ from the Sprint 1 folder, or its files would be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    for bundle_path in sorted(Path(bundle_dir).glob("*.json")):
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        names = [d["file_name"] for d in bundle["documents"]]
        absent = [n for n in names if key(n) not in files]
        if absent:
            sys.exit(f"{bundle['case_number']}: original document(s) not found: {', '.join(absent)}")
        docs = [(n, read(files[key(n)])) for n in names]
        result = evaluate(cat, build_case(bundle["case_number"], docs, bundle))
        output = to_output(result)
        target = out / f"{bundle_path.stem}.json"
        target.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n{to_table(output)}\n flags: {result['review_flags']}\n saved: {target}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
