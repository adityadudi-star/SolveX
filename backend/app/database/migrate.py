"""Schema bootstrap: Alembic is the source of truth. Fresh databases are migrated to head automatically on startup."""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import BACKEND_DIR
from app.database.session import create_all, get_engine


def ensure_schema() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    tables = set(inspect(get_engine()).get_table_names())
    if "alembic_version" in tables or not tables:
        command.upgrade(cfg, "head")            # fresh DB, or already Alembic-managed
    else:
        create_all()                            # legacy/unversioned DB: add missing tables, then adopt Alembic
        command.stamp(cfg, "head")
