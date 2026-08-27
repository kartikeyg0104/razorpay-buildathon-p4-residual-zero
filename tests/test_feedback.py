"""F26 alias table is a dict, not a scorer."""

from __future__ import annotations

from pathlib import Path

from residual_zero.semantic.aliases import AliasTable


def test_alias_round_trip(tmp_path: Path):
    table = AliasTable()
    table.learn("Acme Pvt Ltd", "ent_acme")
    assert table.lookup("acme private limited") == "ent_acme" or table.lookup("Acme Pvt Ltd") == "ent_acme"
    path = tmp_path.joinpath("aliases.json")
    table.save(path)
    loaded = AliasTable.load(path)
    assert loaded.lookup("Acme Pvt Ltd") == "ent_acme"
