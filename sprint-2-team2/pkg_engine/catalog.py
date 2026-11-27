"""Read-only view of Sprint 2 Team 1's NHA package database."""
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .normalize import normalize

DEFAULT_DB = Path(__file__).parents[2] / "sprint-2-team1" / "data" / "final" / "nha_packages.sqlite3"


class Catalog:
    def __init__(self, db_path=DEFAULT_DB):
        if not Path(db_path).is_file():
            raise FileNotFoundError(f"Team 1 database not found: {db_path}")
        con = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT s.specialty_code, s.specialty_name, p.package_id, p.package_code, p.package_name,
                   r.procedure_code, r.procedure_name, r.tier1_price, r.tier2_price, r.tier3_price
            FROM procedures r JOIN packages p USING(package_id) JOIN specialties s USING(specialty_id)
            ORDER BY r.procedure_id""").fetchall()
        # The same code repeats under several specialties: merge identical (code, name) rows.
        merged = {}
        names_per_code = defaultdict(set)
        for r in rows:
            key = (r["procedure_code"], r["procedure_name"].lower())
            names_per_code[r["procedure_code"]].add(r["procedure_name"].lower())
            e = merged.get(key)
            if e is None:
                e = merged[key] = {**dict(r), "package_ids": set(), "specialties": set()}
            e["package_ids"].add(r["package_id"])
            e["specialties"].add(r["specialty_code"])
        self.entries = list(merged.values())
        for e in self.entries:
            e["code_has_conflicting_names"] = len(names_per_code[e["procedure_code"]]) > 1
            e["proc_tokens"] = set(normalize(e["procedure_name"])["tokens"])
            e["pkg_tokens"] = set(normalize(e["package_name"])["tokens"])
        df = Counter(t for e in self.entries for t in e["proc_tokens"] | e["pkg_tokens"])
        self.idf = {t: math.log((1 + len(self.entries)) / (1 + n)) + 1 for t, n in df.items()}
        self.max_idf = math.log(1 + len(self.entries)) + 1
        # Requirements Team 1 may add later are picked up automatically.
        self.team1_requirements = defaultdict(list)
        for table, col in (("package_documents", "document_name"), ("package_investigations", "investigation_name")):
            for r in con.execute(f"SELECT package_id, {col} AS name, requirement_text, source_document, "
                                 f"source_page FROM {table} WHERE mandatory = 1"):
                self.team1_requirements[r["package_id"]].append(dict(r))
        con.close()

    def weight(self, tokens):
        return sum(self.idf.get(t, self.max_idf) for t in tokens)
