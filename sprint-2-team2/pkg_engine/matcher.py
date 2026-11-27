"""Match clinical facts to NHA packages with an explainable heuristic score (0-1).
The score ranks text agreement; it is NOT a probability that the claim is admissible."""
from .normalize import TERMS, normalize, split_code

MATCHED_AT, REVIEW_AT, MARGIN = 0.75, 0.45, 0.10
QUALIFIERS = set(TERMS["qualifiers"])


def _similarity(cat, query, cand):
    common = query & cand
    if not common:
        return 0.0
    return 0.7 * cat.weight(common) / cat.weight(query) + 0.3 * cat.weight(common) / cat.weight(cand)


def _score(cat, entry, term_tokens, dx_tokens, context_tokens, patient, surgical):
    proc = _similarity(cat, term_tokens, entry["proc_tokens"])
    pkg = _similarity(cat, term_tokens, entry["pkg_tokens"])
    both = _similarity(cat, term_tokens, entry["proc_tokens"] | entry["pkg_tokens"])
    score = max(proc, 0.9 * pkg, both if proc else 0.0)    # package + procedure name read together
    if score == 0:
        return None
    reasons = [f"term agreement {score:.2f}"]
    if surgical and dx_tokens:
        core = entry["pkg_tokens"] - QUALIFIERS
        dx = len(core & dx_tokens) / len(core) if core else 0.0
        score = 0.75 * score + 0.25 * dx
        reasons.append(f"diagnosis supports package name {dx:.2f}")
    cand = entry["proc_tokens"] | entry["pkg_tokens"]
    documented = term_tokens | dx_tokens | context_tokens
    for a, b in TERMS["conflicts"]:
        if (a in term_tokens and b in cand and a not in cand) or (b in term_tokens and a in cand and b not in cand):
            score -= 0.4
            reasons.append(f"conflicts: {a} vs {b}")
    unconfirmed = sorted((cand & QUALIFIERS) - documented)
    if unconfirmed:
        score -= min(0.03 * len(unconfirmed), 0.09)
        reasons.append("not documented: " + ", ".join(unconfirmed))
    age = patient.get("age")
    if age is not None and age >= 18 and ("pediatric" in cand or "neonates" in cand or "neonatal" in cand):
        score -= 0.5
        reasons.append(f"child/newborn package but patient is {age}")
    return {"score": round(max(min(score, 1.0), 0.0), 3), "reasons": reasons, "unconfirmed": unconfirmed}


def match_term(cat, name, diagnoses=(), context="", patient=None, surgical=True, top=3):
    patient = patient or {}
    described, stated = split_code(name)
    term = normalize(described)
    term_tokens = set(term["tokens"])
    dx_tokens = {t for d in diagnoses for t in normalize(d)["tokens"]}
    context_tokens = set(normalize(context)["tokens"]) & QUALIFIERS
    scored = []
    for e in cat.entries:
        s = _score(cat, e, term_tokens, dx_tokens, context_tokens, patient, surgical) if term_tokens else None
        if s and s["score"] > 0:
            scored.append((s["score"], e, s))
    scored.sort(key=lambda x: (-x[0], x[1]["procedure_code"]))
    # A code written in the record is checked against the description, never trusted on its own.
    stated_hit = next((x for x in scored if x[1]["procedure_code"] == stated), None)
    agrees = bool(stated_hit) and stated_hit[0] >= REVIEW_AT and scored[0][0] - stated_hit[0] < MARGIN
    if agrees:
        scored.remove(stated_hit)
        scored.insert(0, stated_hit)
    candidates, seen = [], set()
    for score, e, s in scored:
        if e["procedure_code"] in seen:
            continue
        seen.add(e["procedure_code"])
        candidates.append({
            "package_code": e["package_code"], "package_name": e["package_name"],
            "procedure_code": e["procedure_code"], "procedure_name": e["procedure_name"],
            "specialties": sorted(e["specialties"]), "package_ids": sorted(e["package_ids"]),
            "confidence": score, "reasons": s["reasons"], "unconfirmed_attributes": s["unconfirmed"],
            "prices": {k: e[k] for k in ("tier1_price", "tier2_price", "tier3_price")},
            "code_has_conflicting_names": e["code_has_conflicting_names"]})
        if len(candidates) == top:
            break
    flags = []
    best = candidates[0] if candidates else None
    if stated and not agrees:
        flags.append(f"record states code {stated} but the description does not support it")
    if not best or best["confidence"] < REVIEW_AT:
        status = "NO_MATCH"
    else:
        gap = best["confidence"] - (candidates[1]["confidence"] if len(candidates) > 1 else 0)
        if agrees:
            status = "MATCHED"
            best["reasons"].append(f"code {stated} stated in the record agrees with the description")
        elif stated:
            status = "NEEDS_REVIEW"
        elif gap < MARGIN and len(candidates) > 1:
            status = "AMBIGUOUS"
            flags.append(f"top two candidates differ by only {gap:.2f}; a person must choose")
        elif best["confidence"] < MATCHED_AT:
            status = "NEEDS_REVIEW"
        else:
            status = "MATCHED"
        if best["unconfirmed_attributes"]:
            flags.append("confirm in the records: " + ", ".join(best["unconfirmed_attributes"]))
        if best["code_has_conflicting_names"]:
            flags.append("procedure code has differing names in HBP data (pending Team 1 review)")
    return {"input": " ".join(str(name).split()), "stated_code": stated, "normalized": term["normalized"], "laterality": term["laterality"],
            "status": status, "flags": flags, "candidates": candidates}
