"""Database backend abstraction.

The application talks to one narrow DB-API surface — ``execute``, ``executescript``,
``commit``, ``close``, plus cursor iteration and ``fetchone``/``fetchall``. Two backends
implement it:

* **sqlite** (default) — local development, the CLI, the eval harness and the test suite.
  Behaviour is identical to the pre-existing ``residual_zero.db`` module, because it *is*
  that module's connection.
* **postgres** — the authoritative production persistence layer, selected by
  ``RZ_DATABASE_URL``.

Deterministic financial computation stays in Python (:mod:`residual_zero.solver`,
:mod:`residual_zero.verify`). Neither backend performs arithmetic: SQL here is storage
only, which is why one narrow shim can serve both.
"""

from residual_zero.storage.config import Backend, StorageConfig, storage_config

__all__ = ["Backend", "StorageConfig", "storage_config"]
