"""DEV/QA ONLY — seeds a THROWAWAY database with audits of the clearly-fake 'Testco Inc' fixtures so the UI can be exercised without
live SEC access. Never run against the real database:

    python tests/seed_demo_db.py C:/temp/solvex_demo      # creates solvex.db + checkpoints.db in that folder

Then start the API with DATABASE_URL / CHECKPOINT_DB_PATH pointing at those files.
"""
from __future__ import annotations

import sys
import tempfile
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.state import Deps  # noqa: E402
from app.config import Settings  # noqa: E402
from app.database.session import create_all, init_engine  # noqa: E402
from app.services.llm import LLMClient  # noqa: E402
from app.services.sec_client import FilingRef, SecClient  # noqa: E402
from app.workflows.common import clear_caches  # noqa: E402
from app.workflows.runner import WorkflowRunner  # noqa: E402
from tests.fixtures import ACC, BASE, CIK, DOC, FakeSec  # noqa: E402
from datetime import date  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    init_engine(f"sqlite:///{(out / 'solvex.db').as_posix()}")
    create_all()
    scenarios = {
        "normal": {},
        "warning": {"revenue": (1300, 1000, 950)},
        "override": {"revenue": (2500, 1000, 950), "net_income": (400, 100, 95)},
    }
    for i, (name, over) in enumerate(scenarios.items()):
        vals = deepcopy(BASE)
        vals.update(over)
        settings = Settings(sec_contact_email="qa@solvex-test.invalid", cache_dir=str(out / f"cache{i}"), sec_rate_limit_per_sec=10_000,
                            checkpoint_db_path=str(out / "checkpoints.db"))
        fake = FakeSec(values=vals)
        sec = SecClient(settings, transport=fake.transport, sleep=lambda s: None)
        runner = WorkflowRunner(Deps(sec=sec, llm=LLMClient(settings)), checkpoint_path=str(out / "checkpoints.db"))
        clear_caches()
        ref = FilingRef(ACC, "10-K", date(2025, 2, 20), date(2024, 12, 31), DOC, CIK)
        wid, _ = runner.create_audit(ref, "Testco Inc (synthetic fixture)", "TSTC", force_new=True)
        runner.run(wid)
        print(name, wid)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()))
