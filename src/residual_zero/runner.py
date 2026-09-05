"""Record a deterministic reconciliation run into the configured database.

The engine already wrote its results to whichever backend the environment configures —
``open_audit``/``open_verify``/``open_exceptions`` have gone through the storage engine
for a while, so a run inside ``use_tenant`` persisted per-credit uniqueness, residual and
disposition into an organisation's PostgreSQL schema. What was missing was the *run*: the
record that a deterministic execution happened, over which dataset, under which
configuration, and whether it finished.

Without that record a reader cannot distinguish "searched and found nothing" from "never
searched". Both are zero rows. The dashboard was right to refuse to guess.

This module adds only that record and the safety around it. It performs no financial
arithmetic, chooses no candidate, and decides no disposition. The engine decides; this
records that it ran, and refuses to claim a run happened when persistence failed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from residual_zero.audit import (
    RUN_COMPLETED,
    RunConflict,
    begin_run,
    complete_run,
    derive_run_id,
    discard_run,
    find_run,
    open_audit,
)

ENGINE_VERSION = "0.1.0"


class PersistenceError(RuntimeError):
    """The run could not be recorded. Never raised for an engine failure.

    A run is not recorded until persistence succeeds, so this is deliberately loud and
    never falls back to another backend. A local SQLite file standing in for a production
    database would be a reconciliation nobody can find again.
    """


@dataclass(frozen=True)
class RunResult:
    """What happened, split into the two things that can independently fail."""

    run_id: str
    org_id: str
    backend: str
    #: The deterministic engine ran to completion.
    engine_ok: bool
    #: The run reached COMPLETED in the database. Only this makes it a recorded run.
    persisted: bool
    n_processed: int
    reused: bool = False

    @property
    def recorded(self) -> bool:
        return self.engine_ok and self.persisted


def dataset_digest(root: Path) -> str:
    """sha256 over the rendered corpus, so a run's identity includes the data it read.

    Content, not mtime: copying the corpus or rebuilding it byte-identically must produce
    the same digest, and touching a file must not.
    """
    digest = hashlib.sha256()
    if not root.is_dir():
        raise PersistenceError(f"dataset root {root} does not exist")
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _backend_name() -> str:
    from residual_zero.storage.config import storage_config

    return storage_config().backend.value


def require_production_database() -> None:
    """In production the database must be PostgreSQL. No fallback, no local file.

    Checked before the engine starts rather than after, so a misconfigured deployment
    fails without having spent a reconciliation it cannot record.
    """
    from residual_zero.appconfig import load_config
    from residual_zero.storage.config import Backend, storage_config

    if not load_config().is_production:
        return
    if storage_config().backend is not Backend.POSTGRES:
        raise PersistenceError(
            "RZ_ENV=production requires a PostgreSQL RZ_DATABASE_URL to record a run. "
            "Refusing to write a production reconciliation to a local SQLite file: it "
            "would report success and leave nothing anyone else could read."
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_run(
    *,
    tenant,
    split: str,
    limit: int = 0,
    run_id: str | None = None,
    offline: bool = False,
) -> RunResult:
    """Run the deterministic engine for one organisation and record the run.

    The organisation is the tenant already bound by the caller: isolation is the schema,
    so every write below lands in that organisation's namespace without a single query
    having to remember a WHERE clause.
    """
    from residual_zero.config import config_digest, load_fees, load_tax_rates
    from residual_zero.orchestrator import run_split
    from residual_zero.tenancy import use_tenant

    require_production_database()

    root = Path(tenant.dataset_root or Path("data").joinpath(split, "rendered"))
    data_digest = dataset_digest(root)
    cfg_digest = config_digest(load_tax_rates(), load_fees())
    resolved_id = run_id or derive_run_id(
        tenant.org_id, split, root.as_posix(), data_digest, cfg_digest, limit
    )
    backend = _backend_name()

    with use_tenant(tenant):
        audit = open_audit()
        try:
            existing = find_run(audit, resolved_id)
            if existing is not None and existing["status"] == RUN_COMPLETED:
                # Idempotent by identity: same organisation, same data, same configuration.
                # Returning the recorded run is the whole point — re-running would write a
                # second set of results describing the same facts.
                return RunResult(
                    run_id=resolved_id, org_id=tenant.org_id, backend=backend,
                    engine_ok=True, persisted=True,
                    n_processed=int(existing["n_processed"]), reused=True,
                )
            begin_run(
                audit,
                run_id=resolved_id,
                org_id=tenant.org_id,
                split=split,
                dataset_root=root.as_posix(),
                dataset_digest=data_digest,
                config_digest=cfg_digest,
                engine_version=ENGINE_VERSION,
                n_credits=0,
                started_at=_now(),
            )
        finally:
            audit.close()

        engine_ok = False
        try:
            n = run_split(
                split,
                # No path: the organisation's own storage, whichever backend that is.
                # An explicit path always wins in _sqlite_path, so naming a placeholder
                # here would send a tenant's run to that file instead of its ledger.
                None,
                limit=limit,
                offline=offline,
                run_id=resolved_id,
                # A database-backed run has no artifact directory, and inventing one beside
                # a path that names no file is how this used to crash.
                artifact_dir=None,
            )
            engine_ok = True
        except BaseException as exc:
            # The engine failed. Undo what this run wrote rather than leave a partial run
            # that counts as a search.
            closer = open_audit()
            try:
                discard_run(
                    closer, resolved_id,
                    error=f"{type(exc).__name__}: {exc}", finished_at=_now(),
                )
            finally:
                closer.close()
            raise

        audit = open_audit()
        try:
            complete_run(audit, resolved_id, n_processed=n, finished_at=_now())
        except BaseException as exc:
            raise PersistenceError(
                f"the engine processed {n} credits but the run could not be recorded: {exc}"
            ) from exc
        finally:
            audit.close()

    return RunResult(
        run_id=resolved_id, org_id=tenant.org_id, backend=backend,
        engine_ok=engine_ok, persisted=True, n_processed=n,
    )


__all__ = [
    "ENGINE_VERSION",
    "PersistenceError",
    "RunConflict",
    "RunResult",
    "dataset_digest",
    "record_run",
    "require_production_database",
]
