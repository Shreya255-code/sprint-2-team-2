"""Normalize diagnosis / procedure names into comparable tokens."""
import json
import re
from pathlib import Path

TERMS = json.loads((Path(__file__).parents[1] / "config" / "terminology.json").read_text(encoding="utf-8"))


def _replace(text, old, new):
    return re.sub(rf"(?<![a-z]){re.escape(old)}(?![a-z])", new, text)


CODE = re.compile(r"\(?\b([A-Z]{2})([0-9O]{3,4})([A-Z])\b\)?")


def split_code(name):
    """Separate a package code written in the record, e.g. '... (SG050A)'. Fixes OCR letter O for zero."""
    text = str(name or "")
    found = CODE.search(text)
    if not found:
        return text, None
    return " ".join(CODE.sub(" ", text).split()), found[1] + found[2].replace("O", "0") + found[3]


def normalize(name):
    """Return {original, normalized, tokens, laterality}."""
    original = " ".join(str(name or "").split())
    text = original.lower()
    right, left = "right eye" in text or "right knee" in text, "left eye" in text or "left knee" in text
    laterality = "BILATERAL" if "bilateral" in text else "RIGHT" if right else "LEFT" if left else None
    if "bilateral" in text and "operated" in text:          # e.g. "Bilateral cataract (Right Eye operated)"
        laterality = "RIGHT" if right else "LEFT" if left else laterality
    for old, new in TERMS["phrases"].items():
        text = _replace(text, old, new)
    for phrase in TERMS["strip_phrases"]:
        text = text.replace(phrase, " ")
    tokens = [t for t in re.findall(r"[a-z0-9]+", text) if t not in TERMS["stopwords"] and len(t) > 1]
    return {"original": original, "normalized": " ".join(tokens), "tokens": sorted(set(tokens)),
            "laterality": laterality}


def is_investigation(name):
    text = str(name or "").lower().replace("x-ray", "xray").replace("x ray", "xray")
    return any(re.search(rf"\b{re.escape(t)}\b", text) for t in TERMS["investigation_terms"]) \
        and "guided" not in text
