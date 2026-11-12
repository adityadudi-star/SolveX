from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.state import Deps  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.database.session import create_all, init_engine  # noqa: E402
from app.services.llm import LLMClient, set_llm  # noqa: E402
from app.services.sec_client import FilingRef, SecClient, set_sec_client  # noqa: E402
from app.workflows.common import clear_caches  # noqa: E402
from app.workflows.runner import WorkflowRunner, set_runner  # noqa: E402
from tests.fixtures import ACC, CIK, DOC, FakeSec  # noqa: E402

REVIEW_HEADERS = {"X-Reviewer-Token": get_settings().reviewer_token, "X-Reviewer-Name": "Ada Reviewer"}


class Env:
    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.settings = Settings(sec_contact_email="qa@solvex-test.invalid", cache_dir=str(tmp_path / "cache"), sec_rate_limit_per_sec=10_000,
                                 sec_max_retries=2, llm_provider="none", checkpoint_db_path=str(tmp_path / "cp.db"))
        init_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
        create_all()
        clear_caches()
        self.fake: FakeSec | None = None
        self.runner: WorkflowRunner | None = None
        self.client: TestClient | None = None

    def use(self, **kw) -> "Env":
        self.fake = FakeSec(**kw)
        sec = SecClient(self.settings, transport=self.fake.transport, sleep=lambda s: None)
        set_sec_client(sec)
        set_llm(LLMClient(self.settings))
        self.runner = WorkflowRunner(Deps(sec=sec, llm=LLMClient(self.settings)), checkpoint_path=str(self.tmp / "cp.db"))
        set_runner(self.runner)
        clear_caches()
        return self

    @property
    def ref(self) -> FilingRef:
        from datetime import date
        return FilingRef(ACC, "10-K", date(2025, 2, 20), date(2024, 12, 31), DOC, CIK)

    def audit(self, **kw) -> str:
        """Create + run an audit synchronously. Returns workflow id."""
        self.use(**kw) if self.fake is None or kw else None
        wid, _ = self.runner.create_audit(self.ref, "Testco Inc", "TSTC", force_new=True)
        self.runner.run(wid)
        return wid

    def api(self) -> TestClient:
        from app.main import app
        if self.client is None:
            self.client = TestClient(app)
        return self.client


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    import threading
    for t in threading.enumerate():       # let any background resume/start threads finish before the DB is discarded
        if t.name.startswith("solvex-"):
            t.join(30)
    set_runner(None)
    set_sec_client(None)
    set_llm(None)
