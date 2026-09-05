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
    RUN_READABLE,
    RunConflict,
    begin_run,
    complete_run,
    derive_run_id,
    discard_run,
    find_run,
    open_audit,
    persisted_coverage,
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
    """What happened, in numbers that answer different questions.

    ``n_computed`` is invocation-local and ``n_persisted`` is coverage. Conflating them is
    how a run covering 248 credits reported 231: per-credit idempotency made the retry
    skip work already persisted, which is correct, and the loop's tally counted only what
    it did itself, which is also correct — it was the name that lied.
    """

    run_id: str
    org_id: str
    backend: str
    #: The deterministic engine ran to completion.
    engine_ok: bool
    #: The run reached a terminal recorded status. Only this makes it a recorded run.
    persisted: bool
    #: Credits the run was asked to cover. The denominator.
    n_credits: int
    #: Credits this invocation computed. Not coverage.
    n_computed: int
    #: Credits already persisted and correctly skipped rather than recomputed.
    n_reused: int
    #: Credits carrying a persisted result for this run. Coverage, counted from the rows.
    n_persisted: int
    #: COMPLETED or PARTIAL.
    status: str
    reused: bool = False

    @property
    def recorded(self) -> bool:
        return self.engine_ok and self.persisted

    @property
    def complete(self) -> bool:
        """Coverage reaches the dataset. The only meaning of a complete run."""
        return bool(self.n_credits) and self.n_persisted == self.n_credits


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


def input_credit_count(split: str, limit: int = 0) -> int:
    """How many credits this run is asked to cover.

    Read from the same corpus the engine reads — ``data/<split>/rendered`` — because the
    orchestrator loads its credits from there regardless of how a tenant is configured.
    Taking the number from anywhere else would let the denominator drift from the work.
    """
    from residual_zero.ingest.csv_bank import load_bank_credits
    from residual_zero.ingest.source_root import SourceRoot

    credits = load_bank_credits(SourceRoot(Path("data").joinpath(split, "rendered")))
    total = len(credits)
    return min(total, limit) if limit else total


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

    # Bring this organisation's schema up to date before reading or writing a run.
    # Idempotent: it applies pending migrations and returns the versions it applied.
    #
    # Ordering matters and cost me a deploy. run_split calls init_db, which bootstraps the
    # tenant — but the idempotency check reads reconciliation_run *before* that, so on an
    # organisation created before the run table existed the first query failed with
    # UndefinedTable. A schema older than the code is the normal case for a deployed
    # organisation, not an edge case.
    from residual_zero.storage.engine import bootstrap_tenant

    bootstrap_tenant(tenant)

    root = Path(tenant.dataset_root or Path("data").joinpath(split, "rendered"))
    data_digest = dataset_digest(root)
    cfg_digest = config_digest(load_tax_rates(), load_fees())
    resolved_id = run_id or derive_run_id(
        tenant.org_id, split, root.as_posix(), data_digest, cfg_digest, limit
    )
    backend = _backend_name()
    n_input = input_credit_count(split, limit)

    with use_tenant(tenant):
        audit = open_audit()
        try:
            existing = find_run(audit, resolved_id)
            # Complete, not merely COMPLETED. The status alone says the loop finished;
            # `complete` says the dataset is covered, and only that makes re-running
            # pointless. It also means a row written by an older accounting model — one
            # that recorded no coverage at all — is recomputed rather than trusted.
            if existing is not None and existing["complete"]:
                # Idempotent by identity: same organisation, same data, same configuration.
                # Returning the recorded run is the whole point — re-running would write a
                # second set of results describing the same facts.
                #
                # Only a COMPLETED run short-circuits. A PARTIAL one is resumed, because
                # its coverage is incomplete and per-credit idempotency means the retry
                # computes exactly the credits that are missing.
                return RunResult(
                    run_id=resolved_id, org_id=tenant.org_id, backend=backend,
                    engine_ok=True, persisted=True,
                    n_credits=int(existing["n_credits"]),
                    n_computed=0,
                    n_reused=int(existing["n_persisted"]),
                    n_persisted=int(existing["n_persisted"]),
                    status=str(existing["status"]),
                    reused=True,
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
                n_credits=n_input,
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
            status = complete_run(
                audit, resolved_id, n_computed=n, n_credits=n_input, finished_at=_now()
            )
            recorded = find_run(audit, resolved_id) or {}
        except BaseException as exc:
            raise PersistenceError(
                f"the engine computed {n} credits but the run could not be recorded: {exc}"
            ) from exc
        finally:
            audit.close()

    return RunResult(
        run_id=resolved_id, org_id=tenant.org_id, backend=backend,
        engine_ok=engine_ok, persisted=True,
        n_credits=int(recorded.get("n_credits", n_input)),
        n_computed=int(recorded.get("n_computed", n)),
        n_reused=int(recorded.get("n_reused", 0)),
        # Read back rather than remembered: the number a caller sees is the number the
        # database holds, so the two cannot drift.
        n_persisted=int(recorded.get("n_persisted", 0)),
        status=status,
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
