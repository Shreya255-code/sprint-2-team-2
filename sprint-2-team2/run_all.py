"""Sprint 1 (via orchestrator/, Squads 2 and 3) then Sprint 2 Team 2, in one command.
Squad 1 OCR needs a GPU, so run it first from orchestrator/Sprint1_Full_Pipeline.ipynb."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "orchestrator"))

import db_runner  # noqa: E402  (this folder's runner)
from pipeline import Pipeline  # noqa: E402
from pkg_engine.catalog import Catalog  # noqa: E402

if __name__ == "__main__":
    sb = db_runner.connect()
    Pipeline(sb, ROOT).run_until_settled()
    db_runner.run(sb, Catalog())
