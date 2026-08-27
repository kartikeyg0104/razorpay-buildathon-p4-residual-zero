"""Purity against generator cause_labels. Eval-only. Never imported from src/."""

from __future__ import annotations

from collections import Counter, defaultdict

from generator.truth import TruthRecord
from residual_zero.cluster import Cluster


def cluster_purity(
    clusters: tuple[Cluster, ...],
    truth: tuple[TruthRecord, ...],
) -> tuple[int, int]:
    """(majority_correct, n_exceptions). Labels from truth.cause_labels only."""
    by_id = {r.bank_credit_id: r.cause_labels.get("structural", "") for r in truth}
    correct = 0
    n = 0
    for cluster in clusters:
        labels = [by_id.get(cid, "") for cid in cluster.credit_ids]
        n += len(labels)
        if not labels:
            continue
        top = Counter(labels).most_common(1)[0][0]
        correct += sum(1 for lab in labels if lab == top)
    return correct, n
