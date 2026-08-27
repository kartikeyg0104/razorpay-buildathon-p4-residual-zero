"""Bitset DP over the shifted rupee axis. The NN-10 bounds guard lives here."""

from __future__ import annotations

from typing import Sequence


class BudgetExceeded(Exception):
    """Raised internally when a deterministic cap is hit; converted to a SolveResult by solve_search."""


class ReachabilityIndex:
    """Bitset DP over the shifted rupee axis.

    The mask and snapshots are private. The only bit tests are :meth:`is_reachable` and
    :meth:`was_reachable_at`, both of which range-check against ``[NEG, POS]`` first (NN-10).
    """

    def __init__(self, amounts_rupees: Sequence[int]) -> None:
        self._amounts = tuple(int(a) for a in amounts_rupees)
        if any(a == 0 for a in self._amounts):
            raise ValueError("zero amounts are not a legal DP input")
        self.NEG = sum(a for a in self._amounts if a < 0)
        self.POS = sum(a for a in self._amounts if a > 0)
        self.axis_width = self.POS - self.NEG + 1
        # Bit k of the mask means "sum NEG + k is reachable". Empty subset reaches 0.
        reach = 1 << (-self.NEG)
        snapshots = [reach]
        for amount in self._amounts:
            reach |= (reach << amount) if amount >= 0 else (reach >> -amount)
            snapshots.append(reach)
        self._snapshots: tuple[int, ...] = tuple(snapshots)
        self._n = len(self._amounts)

    def _in_range(self, total: int) -> bool:
        return self.NEG <= total <= self.POS

    def _bit(self, mask: int, total: int) -> bool:
        return self._in_range(total) and bool((mask >> (total - self.NEG)) & 1)

    def is_reachable(self, total: int) -> bool:
        """Range-checked bit test on the final mask. Returns False outside [NEG, POS]."""
        return self._bit(self._snapshots[-1], total)

    def was_reachable_at(self, prefix_len: int, total: int) -> bool:
        """Range-checked bit test on snapshot ``prefix_len``. Used only by backtracking."""
        if prefix_len < 0 or prefix_len > self._n:
            return False
        return self._bit(self._snapshots[prefix_len], total)

    def hits_in_window(self, target: int, epsilon: int) -> tuple[int, ...]:
        """Every reachable total in [target-eps, target+eps], ascending. May be empty."""
        if epsilon < 0:
            raise ValueError("epsilon must be non-negative")
        lo = target - epsilon
        hi = target + epsilon
        hits = []
        # Clip the scan to the reachable axis so a huge window cannot walk forever.
        start = lo if lo > self.NEG else self.NEG
        end = hi if hi < self.POS else self.POS
        total = start
        while total <= end:
            if self.is_reachable(total):
                hits.append(total)
            total += 1
        return tuple(hits)

    def nearest_reachable(self, target: int) -> int | None:
        """Closest reachable total to target; its delta is the diagnosis layer's primary input."""
        if self.is_reachable(target):
            return target
        span = max(target - self.NEG, self.POS - target)
        delta = 1
        while delta <= span:
            low = target - delta
            high = target + delta
            # Prefer the lower total on a tie, matching the reference's (target-d, target+d) order.
            if self.is_reachable(low):
                return low
            if self.is_reachable(high):
                return high
            delta += 1
        return None

    def memory_bytes(self) -> int:
        """``(n+1) * axis_width // 8``. Integer because NN-1 forbids true division here."""
        return (self._n + 1) * self.axis_width // 8
