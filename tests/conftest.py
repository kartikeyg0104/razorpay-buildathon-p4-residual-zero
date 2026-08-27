"""Shared CP2 corpora, generated once per test session into a temp tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from generator.cli import generate_split


@pytest.fixture(scope="session")
def cp2_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("rzdata")
    generate_split("dev", Path("config/profiles/phase1.yaml"), root)
    generate_split("test", Path("config/profiles/phase1_test.yaml"), root)
    return root
