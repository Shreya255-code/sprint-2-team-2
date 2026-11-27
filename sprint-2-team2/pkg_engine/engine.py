"""Package matching + document verification for one case."""
from datetime import datetime, timezone

from .matcher import match_term
from .normalize import is_investigation
from .verify import preauth_status, verify

ENGINE_VERSION = "1.4"


def evaluate(cat, case):
    procedures = [p for p in case["procedures"] if not is_investigation(p)]
    context = " ".join(d["text"] for d in case["documents"] if d["type"] == "OPERATIVE_NOTE")
    surgical = bool(procedures)
    terms = procedures or case["diagnoses"]          # medical management: match on diagnosis
    matches = [match_term(cat, t, case["diagnoses"], context, case["patient"], surgical) for t in terms]

    # Different wordings of one procedure must agree on one code.
    matched = [m for m in matches if m["status"] == "MATCHED"]
    codes = {m["candidates"][0]["procedure_code"] for m in matched}
    flags, selected = [], None
    if len(codes) == 1 and all(m["status"] != "AMBIGUOUS" for m in matches):
        selected = max(matched, key=lambda m: m["candidates"][0]["confidence"])["candidates"][0]
        status = "MATCHED"
    elif len(codes) > 1:
        status = "NEEDS_REVIEW"
        flags.append("several different procedure codes matched: " + ", ".join(sorted(codes)))
    elif any(m["status"] == "AMBIGUOUS" for m in matches):
        status = "AMBIGUOUS"
    elif any(m["status"] == "NEEDS_REVIEW" for m in matches):
        status = "NEEDS_REVIEW"
    else:
        status = "NO_MATCH"
    for m in matches:
        if "vitrectomy" in m["normalized"]:
            flags.append("additional step documented (vitrectomy): check for a separate code or complication note")

    # Safety checks. Any one of them sends the case to a person.
    doubts = []
    if len({m["laterality"] for m in matches if m["laterality"] in ("RIGHT", "LEFT")}) > 1:
        doubts.append("documents disagree on laterality (right vs left)")
    unsupported = sorted({m["stated_code"] for m in matches if m["stated_code"] and m["status"] != "MATCHED"})
    if unsupported:
        doubts.append("written package code not confirmed: " + ", ".join(unsupported))
    if len(case.get("medical_record_numbers", [])) > 1:
        doubts.append("documents carry different MRNs: " + ", ".join(case["medical_record_numbers"]))
    if doubts and status == "MATCHED":
        status = "NEEDS_REVIEW"
    if status != "MATCHED":
        selected = None             # a package is kept only for a clean match
    flags += doubts + [f for m in matches for f in m["flags"]]

    checklist, preauth = [], {"status": "unknown"}
    if selected:
        extra = [r for pid in selected["package_ids"] for r in cat.team1_requirements.get(pid, [])]
        checklist = verify(selected, case["documents"], case["treatment_date"], extra)
        preauth = preauth_status(selected["specialties"])

    required = [c for c in checklist if c["verification"] != "PROVISIONAL"]
    missing = [c for c in required if c["status"] in ("MISSING", "EXPIRED")]
    unsure = [c for c in required if c["status"] == "NEEDS_REVIEW"]
    if not selected:
        doc_status = "NOT_CHECKED"
    elif missing:
        doc_status = "INCOMPLETE"
    elif unsure:
        doc_status = "NEEDS_REVIEW"
    else:
        doc_status = "KNOWN_REQUIREMENTS_MET"      # never "complete": package STG not loaded
    return {
        "hospital_name": case.get("hospital_name"), "medication_number": case.get("medication_number"),
        "engine_version": ENGINE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_number": case["case_number"], "patient": case["patient"],
        "treatment_date": str(case["treatment_date"]) if case["treatment_date"] else None,
        "diagnoses": case["diagnoses"], "procedures": procedures,
        "investigations_reported_as_procedures": [p for p in case["procedures"] if p not in procedures],
        "match_status": status, "selected_package": selected, "preauthorization": preauth,
        "review_flags": list(dict.fromkeys(flags)), "term_matches": matches,
        "document_status": doc_status, "checklist": checklist,
        "missing_mandatory_docs": [c["label"] for c in missing],
        "provisional_gaps": [c["label"] for c in checklist
                             if c["verification"] == "PROVISIONAL" and c["status"] != "PRESENT"],
    }


def rfi_draft(result):
    """Request-for-information text for the hospital desk. A person reviews it before sending."""
    p = result["selected_package"]
    lines = [f"RFI DRAFT - case {result['case_number']} (review before sending)"]
    if not p:
        lines.append(f"Package could not be confirmed ({result['match_status']}). Please confirm the exact "
                     "procedure / diagnosis. Candidates:")
        for m in result["term_matches"]:
            lines += [f"  - {c['procedure_code']} {c['procedure_name']}" for c in m["candidates"]]
        if not result["term_matches"]:
            lines.append("  - none: no diagnosis or procedure was extracted")
        return "\n".join(lines)
    lines.append(f"Proposed package: {p['procedure_code']} {p['procedure_name']}")
    for title, keep in (
            ("Please submit:", lambda c: c["verification"] != "PROVISIONAL" and c["status"] in ("MISSING", "EXPIRED")),
            ("Please clarify:", lambda c: c["status"] == "NEEDS_REVIEW"),
            ("Recommended (not confirmed as mandatory):",
             lambda c: c["verification"] == "PROVISIONAL" and c["status"] == "MISSING")):
        items = [c for c in result["checklist"] if keep(c)]
        if items:
            lines.append(title)
            lines += [f"  - {c['label']} [{c['stage']}]" + (f": {c['note']}" if c["status"] != "MISSING" else "")
                      for c in items]
    return "\n".join(lines)
