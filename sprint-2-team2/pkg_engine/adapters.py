"""Turn Sprint 1 output into the engine's case format:
{case_number, patient, diagnoses[], procedures[], treatment_date, documents:[{file_name,type,text}]}"""
import re

from .normalize import split_code
from .verify import classify, parse_date


def _patient(texts):
    for t in texts:
        m = re.search(r"Age\s*/\s*Sex\s*:?\s*(\d{1,3})(?:\s*Years)?\s*/\s*(Male|Female)", t, re.I)
        if m:
            return {"age": int(m[1]), "sex": m[2].title()}
    return {}


def _hospital(documents):
    """Letterhead of a hospital document (not the outside laboratory's)."""
    order = ("DISCHARGE_SUMMARY", "OPERATIVE_NOTE", "CONSENT", "ANAESTHESIA_RECORD")
    for d in sorted((d for d in documents if d["type"] in order), key=lambda d: order.index(d["type"])):
        for line in [x.strip() for x in d["text"].splitlines() if x.strip()][:3]:
            if re.search(r"hospital|centre|center|institute|netralaya|clinic", line, re.I) and len(line) < 80:
                return line
    return None


def _medical_record_numbers(documents):
    return sorted({m.upper() for d in documents for m in re.findall(r"\bMRN-\d+\b", d["text"], re.I)})


def _procedure_names(items):
    """One entry per procedure, keeping a package code that survives only in source_text."""
    names = {}
    for x in items:
        name, code = split_code(x.get("name") or "")
        code = code or split_code(x.get("source_text") or "")[1]
        if name.strip():
            names.setdefault((" ".join(name.lower().split()), code), (" ".join(name.split()), code))
    coded = {n for n, c in names if c}
    return [f"{name} ({code})" if code else name for (n, code), (name, _) in names.items() if code or n not in coded]


def _unique(names):
    out = {}
    for n in names:
        if n and n.strip():
            out.setdefault(" ".join(n.lower().split()), " ".join(n.split()))
    return list(out.values())


def build_case(case_number, documents, bundle):
    """documents: [(file_name, masked_text)]; bundle: Squad 3 master_fhir_bundle_json."""
    docs = [{"file_name": n, "text": t or "", "type": classify(n, t or "")} for n, t in documents]
    treatment = None
    for d in docs:
        m = re.search(r"(?:surgery date|date of surgery)\s*:?\s*([0-9/\-]+)", d["text"], re.I)
        treatment = treatment or (parse_date(m[1]) if m else None)
    if not treatment:
        dates = [p.get("event_date") for p in bundle.get("procedures", [])] + [bundle.get("admission_date")]
        treatment = next((parse_date(x) for x in dates if x), None)
    numbers = _medical_record_numbers(docs)
    return {"case_number": case_number, "hospital_name": _hospital(docs),
            "medication_number": numbers[0] if len(numbers) == 1 else None,
            "medical_record_numbers": numbers, "patient": _patient([d["text"] for d in docs]),
            "diagnoses": _unique(x.get("name") for x in bundle.get("diagnoses", [])),
            "procedures": _procedure_names(bundle.get("procedures", [])),
            "treatment_date": treatment, "documents": docs}


def bundle_from_labels(documents):
    """OFFLINE DEMO ONLY: read 'Diagnosis:' / 'Procedure:' labels instead of calling Squad 3 (Gemini)."""
    found = {"diagnoses": [], "procedures": []}
    for _, text in documents:
        for key, label in (("diagnoses", "diagnosis"), ("procedures", "procedure")):
            for m in re.finditer(rf"^{label}\s*:[ \t]*\n?[ \t]*(.+)$", text, re.I | re.M):
                found[key].append({"name": m[1].strip()})
    return found
