from datetime import date

import pytest

import db_runner
from match_case import SAMPLE, load
from pkg_engine.adapters import build_case
from pkg_engine.catalog import Catalog
from pkg_engine.engine import evaluate, rfi_draft
from pkg_engine.matcher import match_term
from pkg_engine.report import to_output, to_table


@pytest.fixture(scope="module")
def cat():
    return Catalog()


def make(diagnoses, procedures, documents=(), age=60):
    docs = [("Discharge_Summary", f"Age / Sex\n{age} / Male\nSurgery Date\n09/11/2024"), *documents]
    return build_case("T", docs, {"diagnoses": [{"name": d} for d in diagnoses],
                                  "procedures": [{"name": p} for p in procedures]})


def item(result, rule_id):
    return next(c for c in result["checklist"] if c["id"] == rule_id)


@pytest.mark.parametrize("term,code", [("TKR primary", "SB039A"), ("Lap appendectomy", "SG017B"),
                                       ("Phaco with foldable hydrophobic acrylic IOL", "SE020A")])
def test_abbreviations(cat, term, code):
    assert match_term(cat, term)["candidates"][0]["procedure_code"] == code


def test_medical_case_ignores_investigations(cat):
    r = evaluate(cat, make(["community-acquired pneumonia"], ["chest X-ray", "complete blood count (CBC)"]))
    assert r["selected_package"]["procedure_code"] == "MG016A"
    assert r["procedures"] == [] and len(r["investigations_reported_as_procedures"]) == 2


def test_unspecified_variant_is_not_auto_selected(cat):
    r = evaluate(cat, make(["appendicitis"], ["appendicectomy"]))
    assert r["match_status"] == "AMBIGUOUS" and r["selected_package"] is None
    assert r["document_status"] == "NOT_CHECKED" and "SG017" in rfi_draft(r)


def test_unknown_and_empty_do_not_match(cat):
    assert evaluate(cat, make(["xyzzy syndrome"], []))["match_status"] == "NO_MATCH"
    assert evaluate(cat, make([], []))["match_status"] == "NO_MATCH"


def test_adult_never_gets_paediatric_package(cat):
    m = match_term(cat, "cataract surgery", ["cataract"], patient={"age": 62})
    assert m["candidates"][0]["package_code"] != "SE021"


def test_mention_is_not_evidence(cat):
    note = ("Operative_Report", "ECG normal. IOL sticker attached. Haemoglobin 13")
    r = evaluate(cat, make(["cataract"], ["phaco with foldable hydrophobic acrylic IOL"], [note]))
    for rule in ("ecg", "iol_barcode", "haemoglobin"):
        assert item(r, rule)["status"] == "MISSING"
    assert "ECG report" not in r["missing_mandatory_docs"]          # provisional rule


@pytest.mark.parametrize("collected,status", [("06/11/2024", "PRESENT"), ("01/09/2024", "EXPIRED"),
                                              ("10/11/2024", "EXPIRED"), ("??", "NEEDS_REVIEW")])
def test_lab_validity(cat, collected, status):
    lab = ("Lab_Report", f"Sample Collected\n{collected}\nHaemoglobin\n13.2 gm%")
    r = evaluate(cat, make(["cataract"], ["phaco foldable hydrophobic acrylic IOL"], [lab]))
    assert r["treatment_date"] == str(date(2024, 11, 9))
    assert item(r, "haemoglobin")["status"] == status


def test_sprint1_samples(cat):
    results = {c["case_number"]: evaluate(cat, c) for c in load(SAMPLE)}
    for n in "1234":
        assert results[f"Patient_0{n}"]["selected_package"]["procedure_code"] == "SE020A"
    assert results["Patient_05"]["match_status"] != "MATCHED"        # vitrectomy needs a person


class FakeDB:
    """Minimal stand-in for the supabase client."""
    def __init__(self, cases, docs):
        self.data = {"claims_cases": cases, "claim_documents": docs}
        self.writes = []

    def table(self, name):
        db = self

        class Query:
            rows, update_data = list(db.data[name]), None

            def select(self, *_):
                return self

            def eq(self, col, value):
                self.rows = [r for r in self.rows if r.get(col) == value]
                return self

            def update(self, data):
                self.update_data = data
                return self

            def execute(self):
                if self.update_data is not None:
                    for r in self.rows:
                        r.update(self.update_data)
                    db.writes.append(self.update_data)
                return type("R", (), {"data": self.rows})
        return Query()


def fake(**extra):
    case = {"case_id": 1, "case_number": "C1", "pipeline_stage": "COMPLETED", "case_audit_summary": {"other": 1},
            "master_fhir_bundle_json": {"diagnoses": [{"name": "Mature cataract"}], "procedures": [
                {"name": "Phaco with foldable hydrophobic acrylic IOL"}]}, **extra}
    return FakeDB([case], [{"case_id": 1, "file_name": "Discharge_Summary.pdf",
                            "redacted_ocr_json": {"masked_text": "Age/Sex: 60/Male"}}]), case


def test_db_write_and_rerun(cat):
    sb, case = fake()
    assert db_runner.run(sb, cat, dry=True) == 1 and not sb.writes
    assert db_runner.run(sb, cat) == 1
    assert case["package_code"] == "SE020" and "Discharge summary" not in case["missing_mandatory_docs"]
    assert case["case_audit_summary"]["other"] == 1 and case["pipeline_stage"] == "COMPLETED"
    assert "admissibility_score" not in sb.writes[0] and "case_status" not in sb.writes[0]
    assert db_runner.run(sb, cat) == 0


def test_db_never_overwrites_human_value(cat):
    sb, case = fake(package_code="SE999")
    db_runner.run(sb, cat)
    db_runner.run(sb, cat, force=True)
    assert case["package_code"] == "SE999"


def test_output_format(cat):
    out = to_output(evaluate(cat, make(["cataract"], ["phaco foldable hydrophobic acrylic IOL"])), case_id=7)
    assert list(out) == ["case_id", "case_number", "medication_number", "diagnosis", "procedure",
                         "hospital_name", "package_match", "completeness"] and out["case_id"] == "7"
    assert out["package_match"] == {"status": "MATCHED", "selected_package_code": "SE020"}
    rows = {r["document_name"]: r for r in out["completeness"]["requirements"]}
    assert rows["Discharge summary"]["status"] == "PRESENT" and "reason" not in rows["Discharge summary"]
    assert rows["Patient photograph"]["reason"] and rows["Patient photograph"]["source_reference"]
    assert "ECG report" not in rows and "ECG report" in out["completeness"]["recommended_not_mandatory"]
    assert "Patient photograph" in to_table(out)
    empty = to_output(evaluate(cat, make([], [])))
    assert empty["package_match"]["selected_package_code"] is None and empty["completeness"]["requirements"] == []


@pytest.mark.parametrize("term,code", [
    ("Right Inguinal Hernia Repair - Open (SGO50A)", "SG050A"),
    ("Laparoscopic Appendicectomy (SG017B)", "SG017B"),
    ("Laparoscopic Cholecystectomy Without CBD Exploration (SG039C)", "SG039C")])
def test_stated_code_that_agrees(cat, term, code):
    m = match_term(cat, term)
    assert m["status"] == "MATCHED" and m["candidates"][0]["procedure_code"] == code


@pytest.mark.parametrize("term", ["Laparoscopic Appendicectomy (SE020A)",
                                  "Laparoscopic Cholecystectomy Without CBD Exploration (SG039D)",
                                  "Laparoscopic Appendicectomy (ZZ999Z)"])
def test_wrong_stated_code_goes_to_review(cat, term):
    r = evaluate(cat, make([], [term]))
    assert r["selected_package"] is None and any("record states code" in f for f in r["review_flags"])


def test_inguinal_is_not_confused_with_femoral(cat):
    m = match_term(cat, "Right Inguinal Hernia Repair - Open", ["Right Inguinal Hernia"])
    assert m["candidates"][0]["procedure_code"] == "SG050A" and m["status"] == "MATCHED"


def test_header_fields_and_code_from_source_text(cat):
    docs = [("Discharge_Summary.pdf", "   SAI CARE HOSPITAL\n DISCHARGE SUMMARY\nMedication / MRN No.   MRN-12")]
    bundle = {"diagnoses": [{"name": "Acute Appendicitis"}], "procedures": [
        {"name": "Laparoscopic Appendicectomy", "source_text": "Procedure: Laparoscopic Appendicectomy (SG017B)"},
        {"name": "OCULAR BIOMETRY / A-SCAN"}]}
    out = to_output(evaluate(cat, build_case("C", docs, bundle)))
    assert (out["hospital_name"], out["medication_number"]) == ("SAI CARE HOSPITAL", "MRN-12")
    assert out["procedure"] == "Laparoscopic Appendicectomy" and out["diagnosis"] == "Acute Appendicitis"
    assert out["package_match"]["selected_package_code"] == "SG017"


def test_mixed_patient_documents_are_flagged(cat):
    docs = [("Discharge_Summary.pdf", "MRN-1"), ("Lab_Report.png", "MRN-2")]
    r = evaluate(cat, build_case("C", docs, {"procedures": [{"name": "Lap Appendicectomy (SG017B)"}]}))
    assert r["match_status"] == "NEEDS_REVIEW" and r["selected_package"] is None
    assert to_output(r)["medication_number"] is None


@pytest.mark.parametrize("procedures,documents", [
    (["Right eye phaco foldable hydrophobic acrylic IOL", "Left eye phaco foldable hydrophobic acrylic IOL"], []),
    (["Laparoscopic Appendicectomy (SG017B)", "Laparoscopic Appendicectomy (SE020A)"], []),
    (["Laparoscopic Appendicectomy (SG017B)", "Hernia repair (ZZ999Z)"], []),
    (["Right Lap Appendicectomy (SG017B)", "Left Lap Appendicectomy (SG017B)"],
     [("Lab_Report", "MRN-1"), ("OT_Notes", "MRN-2")])])
def test_a_doubtful_case_never_keeps_a_package(cat, procedures, documents):
    r = evaluate(cat, make([], procedures, documents))
    assert r["match_status"] != "MATCHED" and r["selected_package"] is None
    assert r["document_status"] == "NOT_CHECKED" and r["checklist"] == []
    assert to_output(r)["package_match"]["selected_package_code"] is None
