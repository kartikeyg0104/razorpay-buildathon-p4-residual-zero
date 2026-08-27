"""Load a merchant profile. Thin wrapper so the generator does not import config internals."""

from __future__ import annotations

from pathlib import Path

from residual_zero.config import MerchantProfile, load_profile

SPLIT_SEEDS: dict[str, tuple[int, ...]] = {
    "dev": (1, 2, 3),
    "test": (101, 102, 103, 104, 105),
    "devscale": (11, 12, 13, 14, 15, 16, 17, 18),
}


def load(path: str | Path) -> MerchantProfile:
    return load_profile(Path(path))
