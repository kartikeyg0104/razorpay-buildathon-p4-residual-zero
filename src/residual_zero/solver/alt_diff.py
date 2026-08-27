"""F36: symmetric difference of two surviving decompositions, for a human."""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(frozen=True, extra="forbid")


class AlternateDiff(BaseModel):
    model_config = _STRICT

    only_a: tuple[str, ...]
    only_b: tuple[str, ...]
    shared: tuple[str, ...]
    symmetric_difference_size: int = Field(ge=0)
    size_a: int = Field(ge=0)
    size_b: int = Field(ge=0)


def diff_sets(a: Sequence[str], b: Sequence[str]) -> AlternateDiff:
    """Present the symmetric difference, not the union, of two member-id tuples."""
    sa, sb = set(a), set(b)
    only_a = tuple(sorted(sa - sb))
    only_b = tuple(sorted(sb - sa))
    shared = tuple(sorted(sa & sb))
    return AlternateDiff(
        only_a=only_a,
        only_b=only_b,
        shared=shared,
        symmetric_difference_size=len(only_a) + len(only_b),
        size_a=len(sa),
        size_b=len(sb),
    )


def median_int(values: Sequence[int]) -> int | None:
    """Lower median of a non-empty integer list. Empty → None (caller renders as N/A)."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        return ordered[n // 2]
    return ordered[n // 2 - 1]


def pair_stats(
    pool_ids: Sequence[str],
    enumerated: Sequence[Sequence[int]],
    feasible_indices: Sequence[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return (symdiff sizes of every feasible pair, decomposition sizes of every feasible set)."""
    members: list[tuple[str, ...]] = []
    for idx in feasible_indices:
        ids = tuple(sorted(pool_ids[i] for i in enumerated[idx]))
        members.append(ids)
    sizes = tuple(len(m) for m in members)
    diffs: list[int] = []
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            diffs.append(diff_sets(members[i], members[j]).symmetric_difference_size)
    return tuple(diffs), sizes


def render_diff(diff: AlternateDiff) -> str:
    """The text a human reads instead of two full member lists."""
    a = ", ".join(diff.only_a) if diff.only_a else "—"
    b = ", ".join(diff.only_b) if diff.only_b else "—"
    return (
        f"only A: {a}\n"
        f"only B: {b}\n"
        f"shared: {len(diff.shared)}\n"
        f"symmetric-difference size: {diff.symmetric_difference_size}\n"
        f"decomposition sizes: {diff.size_a}, {diff.size_b}"
    )
