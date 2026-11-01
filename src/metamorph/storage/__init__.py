"""Run storage (SQLite by default)."""

from metamorph.storage.repo import Store, sqlite_url

__all__ = ["Store", "sqlite_url"]
