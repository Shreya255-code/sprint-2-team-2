"""Check which required documents / investigations are actually present in a case."""
import json
import re
from datetime import date
from pathlib import Path

CONFIG = json.loads((Path(__file__).parents[1] / "config" / "requirements.json").read_text(encoding="utf-8"))


def classify(file_name, text):
    """Type of one document. File name first, then the heading of the text."""
    for source in (file_name.lower(), text[:300].lower()):
        s = re.sub(r"[_\-]+", " ", source)
        for kind, pattern in (
                ("DISCHARGE_MEDICATIONS", r"discharge medication"),
                ("DISCHARGE_SUMMARY", r"discharge summary"),
                ("OPERATIVE_NOTE", r"operative|surgical procedur|ot note"),
                ("BIOMETRY", r"biometry|a scan|keratometry"),
                ("ANAESTHESIA_RECORD", r"an(a)?esthesia record"),
                ("CONSENT", r"consent"),
                ("ECG", r"\becg\b|electrocardiogra"),
                ("RADIOLOGY", r"x ?ray report|\bmri\b|ct scan|radiology|usg report|\busg\b|ultrasound|\bx ?ray\b"),
                ("LAB_REPORT", r"lab report|haemogram|biochemistry|pathology"),
                ("IOL_STICKER", r"iol sticker|lens sticker|implant sticker|barcode"),
                ("HISTOPATHOLOGY", r"histopath"),
                ("PHOTO", r"photo")):
            if re.search(pattern, s):
                return kind
    return "OTHER"


def parse_date(value):
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", value or "")
    try:
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))        # Indian dd/mm/yyyy
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _has_result(text, test):
    """A test counts only when a numeric value follows its name (a mere mention does not)."""
    return re.search(rf"(?:{test})[^\n]{{0,15}}\s*\n?\s*:?\s*\d", text, re.I) is not None


# evidence key -> (document types that can prove it, text test or None)
EVIDENCE = {
    "discharge_summary": (("DISCHARGE_SUMMARY",), None),
    "clinical_notes": (("DISCHARGE_SUMMARY", "OPERATIVE_NOTE", "CLINICAL_NOTES"), None),
    "operative_note": (("OPERATIVE_NOTE",), None),
    "biometry": (("BIOMETRY",), None),
    "ecg": (("ECG",), None),
    "iol_sticker": (("IOL_STICKER",), None),
    "patient_photo": (("PHOTO",), None),
    "treatment_photos": (("PHOTO",), None),
    "usg_abdomen": (("RADIOLOGY",), lambda t: re.search(r"ultrasound|\busg\b", t, re.I)),
    "xray": (("RADIOLOGY",), lambda t: re.search(r"x[ -]?ray|radiograph", t, re.I)),
    "implant_sticker": (("IOL_STICKER",), None),
    "consent": (("CONSENT",), None),
    "histopathology": (("HISTOPATHOLOGY",), None),
    "mri": (("RADIOLOGY",), lambda t: re.search(r"\bmri\b", t, re.I)),
    "chest_xray": (("RADIOLOGY",), lambda t: re.search(r"chest", t, re.I)),
    "haemoglobin": (("LAB_REPORT",), lambda t: _has_result(t, r"ha?emoglobin|\bHb\b")),
    "renal_function": (("LAB_REPORT",), lambda t: _has_result(t, "creatinine")),
}


def check_rule(rule, documents, reference_date):
    types, test = EVIDENCE[rule["evidence"]]
    found = [d for d in documents if d["type"] in types and (test is None or test(d["text"]))]
    if rule["evidence"] == "treatment_photos" and found:
        names = " ".join(d["file_name"].lower() for d in found)
        if not all(re.search(p, names) for p in ("pre|before", "intra|during", "post|after")):
            return "NEEDS_REVIEW", found, "photos present but before/during/after not identifiable"
    if not found:
        return "MISSING", [], "no matching document in the case"
    if rule.get("max_age_days"):
        dates = []
        for d in found:
            m = re.search(r"(?:sample collected|collected on|reported on)\s*:?\s*([0-9/\-]+)", d["text"], re.I)
            dates.append(parse_date(m[1]) if m else None)
        known = [x for x in dates if x]
        if not known or not reference_date:
            return "NEEDS_REVIEW", found, "report or treatment date not readable"
        age = (reference_date - max(known)).days
        if age > rule["max_age_days"] or age < 0:
            return "EXPIRED", found, f"report is {age} days before treatment (allowed 0-{rule['max_age_days']})"
    return "PRESENT", found, ""


def verify(package, documents, reference_date, team1_requirements=()):
    rules = [r for r in CONFIG["rules"]
             if "*" in r["applies_to"] or package["package_code"] in r["applies_to"]
             or any(w in package["package_name"].lower() for w in r.get("applies_to_name_contains", []))]
    checklist = []
    for r in rules:
        status, found, note = check_rule(r, documents, reference_date)
        checklist.append({"id": r["id"], "label": r["label"], "stage": r["stage"], "status": status, "note": note,
                          "verification": r["verification"], "source": CONFIG["sources"][r["source"]],
                          "reference": r["ref"], "evidence_documents": [d["file_name"] for d in found]})
    for r in team1_requirements:                         # no automatic detector yet -> person checks
        checklist.append({"id": "team1:" + r["name"], "label": r["name"], "stage": "PREAUTH",
                          "status": "NEEDS_REVIEW", "note": r["requirement_text"], "verification": "TEAM1_DB",
                          "source": r["source_document"], "reference": f"page {r['source_page']}",
                          "evidence_documents": []})
    return checklist


def preauth_status(specialties):
    for s in specialties:
        if s in CONFIG["preauth_by_specialty"]:
            return CONFIG["preauth_by_specialty"][s]
    return {"status": "unknown"}
