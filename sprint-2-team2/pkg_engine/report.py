"""The agreed output format (JSON) and a text table of the same data."""


from .normalize import split_code


def _row(number, item):
    row = {"requirement_id": f"REQ-{number:03d}", "document_name": item["label"], "status": item["status"]}
    if item["status"] != "PRESENT":
        row["reason"] = item["note"] or "Required document not found."
        source = item["source"].split(", http")[0]
        row["source_reference"] = source + (f", section {item['reference']}" if item["reference"] else "")
    return row


def to_output(result, case_id=None):
    """requirement_id numbers rows within one case; it is not a permanent ID."""
    selected = result["selected_package"]
    required = [c for c in result["checklist"] if c["verification"] != "PROVISIONAL"]
    candidates = []
    for term in result.get("term_matches", []):
        for candidate in term.get("candidates", []):
            candidates.append({
                "input": term["input"],
                "term_match_status": term["status"],
                "package_code": candidate["package_code"],
                "package_name": candidate["package_name"],
                "procedure_code": candidate["procedure_code"],
                "procedure_name": candidate["procedure_name"],
                "confidence_score": candidate["confidence"],
                "reasons": candidate["reasons"],
                "unconfirmed_attributes": candidate["unconfirmed_attributes"],
            })
    confidence = (selected["confidence"] if selected else
                  max((c["confidence_score"] for c in candidates), default=None))
    output = {
        "case_id": str(case_id or result["case_number"]),
        "case_number": result["case_number"],
        "medication_number": result.get("medication_number"),      # the MRN printed on the documents
        "diagnosis": result["diagnoses"][0] if result["diagnoses"] else None,
        "procedure": split_code(result["procedures"][0])[0] if result["procedures"] else None,
        "hospital_name": result.get("hospital_name"),
        "package_match": {"status": result["match_status"],
                          "selected_package_code": selected["package_code"] if selected else None,
                          "confidence_score": confidence,
                          "candidates": candidates,
                          "review_flags": result.get("review_flags", [])},
        "completeness": {"status": result["document_status"],
                         "requirements": [_row(i, c) for i, c in enumerate(required, 1)]},
    }
    recommended = [c["label"] for c in result["checklist"]
                   if c["verification"] == "PROVISIONAL" and c["status"] != "PRESENT"]
    if recommended:                      # unconfirmed rules are kept apart from real requirements
        output["completeness"]["recommended_not_mandatory"] = recommended
    return output


def to_table(output):
    match, done = output["package_match"], output["completeness"]
    lines = [f"Case {output['case_number']} | match: {match['status']} | package: "
             f"{match['selected_package_code'] or '-'} | documents: {done['status']}"]
    rows = [("ID", "Document", "Status")] + [(r["requirement_id"], r["document_name"], r["status"])
                                           for r in done["requirements"]]
    if len(rows) == 1:
        return lines[0] + "\n(documents not checked)"
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    for n, r in enumerate(rows):
        lines.append(" | ".join(v.ljust(w) for v, w in zip(r, widths)))
        if n == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return "\n".join(lines)
