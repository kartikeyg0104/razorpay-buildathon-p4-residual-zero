"""Fit an integer bag-of-words controller on this ledger and eval artifacts.

No live model. No float money. Never writes CLEARED.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from residual_zero.db import open_readonly
from residual_zero.exceptions.narrate import TEMPLATES as DIAGNOSIS
from residual_zero.models import ExceptionClass
from residual_zero.qa.corpus import LABELS, CorpusDoc, load_documents
from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = frozenset(
    {
        "the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and", "or",
        "this", "that", "it", "be", "at", "by", "from", "with",
    }
)


class Fitted(NamedTuple):
    weights: dict[str, dict[str, int]]
    n_train: int
    n_holdout: int
    n_holdout_ok: int
    n_credits: int
    n_docs: int
    n_labels: int


def tokenize(text: str) -> tuple[str, ...]:
    out = []
    for raw in _TOKEN.findall(text.casefold()):
        if raw in _STOP or len(raw) < 2:
            continue
        if raw.startswith("crd_"):
            continue
        out.append(raw)
    return tuple(out)


def _diagnosis_text(cls: ExceptionClass) -> str:
    template = DIAGNOSIS[cls]
    filled = template
    for key in ("DELTA", "GROSS", "PCT", "ALTERNATES", "DUPLICATES"):
        filled = filled.replace("{" + key + "}", "—")
    return filled


def _db_path() -> Path:
    env_path = os.environ.get("RZ_DB")
    if env_path:
        return Path(env_path)
    primary = Path("artifacts").joinpath("dev", "ledger.sqlite")
    if primary.is_file():
        return primary
    return Path("artifacts").joinpath("dev", "cp5", "ledger.sqlite")


def _exception_counts() -> dict[str, int]:
    path = _db_path()
    if not path.is_file():
        return {}
    conn = open_readonly(path)
    try:
        rows = conn.execute(
            "SELECT exception_class, COUNT(*) FROM exception GROUP BY exception_class"
        ).fetchall()
    # QUERY_ERRORS, not sqlite3.OperationalError: the equivalent PostgreSQL error is a
    # different class, so a name-based except stopped degrading the moment Postgres
    # became a backend and a missing table became a 500. rollback_quietly clears the
    # aborted transaction Postgres leaves behind, so the next query on this connection
    # can still run.
    except QUERY_ERRORS:
        rollback_quietly(conn)
        rows = []
    finally:
        conn.close()
    return {str(name): int(n) for name, n in rows}


def _n_credits() -> int:
    rendered = Path("data").joinpath("dev", "rendered")
    if not rendered.is_dir():
        return 0
    from residual_zero.ingest.csv_bank import load_bank_credits
    from residual_zero.ingest.source_root import SourceRoot

    return len(load_bank_credits(SourceRoot(rendered)))


def ledger_documents() -> tuple[CorpusDoc, ...]:
    """One document per exception class, counts from this sqlite queue."""
    counts = _exception_counts()
    docs = []
    for cls in ExceptionClass:
        n = counts.get(cls.value, 0)
        docs.append(
            CorpusDoc(
                "exc_" + cls.value,
                cls.value.replace("_", " ").lower(),
                (
                    f"{n} credits in the local queue are {cls.value}. "
                    f"{_diagnosis_text(cls)} Overlay does not write CLEARED."
                ),
                "exception",
            )
        )
    return tuple(docs)


def all_documents() -> tuple[CorpusDoc, ...]:
    return load_documents() + ledger_documents()


def _examples(docs: tuple[CorpusDoc, ...]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = list(LABELS)
    for doc in docs:
        pairs.append((doc.title, doc.id))
        if doc.id.startswith("exc_"):
            cls = doc.id[4:]
            pairs.append(("what is " + cls.replace("_", " "), doc.id))
            pairs.append(("why " + cls.replace("_", " "), doc.id))
    return pairs


def _fit_weights(examples: list[tuple[str, str]], docs: tuple[CorpusDoc, ...]) -> dict[str, dict[str, int]]:
    by_doc: dict[str, Counter[str]] = {}
    for doc in docs:
        bag = by_doc.setdefault(doc.id, Counter())
        bag.update(tokenize(doc.title + " " + doc.body))
    for question, doc_id in examples:
        by_doc.setdefault(doc_id, Counter()).update(tokenize(question))
    n_docs = max(1, len(by_doc))
    df: Counter[str] = Counter()
    for bag in by_doc.values():
        df.update(set(bag))
    weights: dict[str, dict[str, int]] = {}
    for doc_id, bag in by_doc.items():
        w: dict[str, int] = {}
        for token, tf in bag.items():
            idf = n_docs // max(1, df[token])
            w[token] = tf * (1 + idf)
        weights[doc_id] = w
    return weights


def predict_doc(weights: dict[str, dict[str, int]], question: str) -> tuple[str, int]:
    counts = Counter(tokenize(question))
    if not counts:
        return "", 0
    best_id = ""
    best = 0
    for doc_id, table in weights.items():
        score = 0
        for token, n in counts.items():
            score += n * table.get(token, 0)
        if score > best:
            best = score
            best_id = doc_id
    return best_id, best


def train() -> Fitted:
    """Fit on policy labels + exception-class histogram from this corpus."""
    docs = all_documents()
    examples = _examples(docs)
    train_ex = [ex for i, ex in enumerate(examples) if i % 5 != 4]
    hold_ex = [ex for i, ex in enumerate(examples) if i % 5 == 4]
    weights = _fit_weights(train_ex, docs)
    ok = 0
    for question, want in hold_ex:
        got, _score = predict_doc(weights, question)
        if got == want:
            ok += 1
    return Fitted(
        weights=weights,
        n_train=len(train_ex),
        n_holdout=len(hold_ex),
        n_holdout_ok=ok,
        n_credits=_n_credits(),
        n_docs=len(docs),
        n_labels=len(LABELS),
    )


@lru_cache(maxsize=1)
def trained() -> Fitted:
    return train()
