"""Test the engine on a folder of patient folders (PDF / image documents).
   python run_folder.py <patients_dir>
Needs `pdftotext` (poppler) and `tesseract` installed. This is a LOCAL TEST substitute for Sprint 1:
no PII masking and no Gemini extraction, so use synthetic data only."""
import json
import subprocess
import sys
from pathlib import Path

from pkg_engine.adapters import build_case, bundle_from_labels
from pkg_engine.catalog import Catalog
from pkg_engine.engine import evaluate, rfi_draft
from pkg_engine.report import to_output, to_table

KINDS = {".pdf", ".png", ".jpg", ".jpeg"}


def read(path):
    command = (["pdftotext", "-layout", str(path), "-"] if path.suffix.lower() == ".pdf"
               else ["tesseract", str(path), "-", "--psm", "6"])
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


def main(root):
    cat, out = Catalog(), Path(__file__).parent / "outputs"
    out.mkdir(exist_ok=True)
    for folder in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        docs = [(f.name, read(f)) for f in sorted(folder.iterdir()) if f.suffix.lower() in KINDS]
        result = evaluate(cat, build_case(folder.name, docs, bundle_from_labels(docs)))
        output = to_output(result)
        (out / f"{folder.name}.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"\n{to_table(output)}")
        recommended = output["completeness"].get("recommended_not_mandatory")
        if recommended:
            print("Recommended, not confirmed mandatory:", "; ".join(recommended))
        result["rfi_draft"] = rfi_draft(result)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
