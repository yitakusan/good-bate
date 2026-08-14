from __future__ import annotations

"""Isolate unittest sqlite files. Never touch production or the shared shadow DB."""

import os
import tempfile
import unittest
from pathlib import Path

from app.database import DATA_DIR, get_db_path, init_db
from app.settings import get_settings

PRODUCTION_DB = DATA_DIR / "stockgood.sqlite"
SHADOW_DB = DATA_DIR / "stockgood.shadow.sqlite"


def isolate_db(*, auth_required: bool = False, admin_token: str | None = None) -> Path:
    fd, raw = tempfile.mkstemp(prefix="stockgood-test-", suffix=".sqlite")
    os.close(fd)
    path = Path(raw)
    os.environ["STOCKGOOD_DB_MODE"] = "shadow"
    os.environ["STOCKGOOD_DATABASE_PATH"] = str(path)
    os.environ["STOCKGOOD_AUTH_REQUIRED"] = "true" if auth_required else "false"
    os.environ["STOCKGOOD_SESSION_SECRET"] = "stockgood-test-session"
    if admin_token:
        os.environ["STOCKGOOD_ADMIN_TOKEN"] = admin_token
    else:
        os.environ.pop("STOCKGOOD_ADMIN_TOKEN", None)
    get_settings.cache_clear()
    resolved = get_db_path().resolve()
    if resolved != path.resolve():
        raise RuntimeError(f"test DB isolation failed: {resolved} != {path}")
    if resolved in (PRODUCTION_DB.resolve(), SHADOW_DB.resolve()):
        raise RuntimeError("refusing to run tests against production or shared shadow sqlite")
    if resolved.name == "stockgood.sqlite":
        raise RuntimeError("refusing to run tests against production sqlite")
    return resolved


def _unlink_sqlite(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix) if suffix else path
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


class IsolatedDbTestCase(unittest.TestCase):
    auth_required = False
    admin_token: str | None = None
    auto_init_db = True

    def setUp(self) -> None:
        self.db_path = isolate_db(
            auth_required=self.auth_required,
            admin_token=self.admin_token,
        )
        self.addCleanup(_unlink_sqlite, self.db_path)
        if self.auto_init_db:
            init_db()
