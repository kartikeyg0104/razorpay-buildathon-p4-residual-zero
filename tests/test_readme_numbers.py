"""README numbers come from committed artifacts. Spec placeholders stay labelled as such."""

from __future__ import annotations

import re
from pathlib import Path

SPEC_FIGURES = ("0.942", "0.0008", "200:9", "47,200", "2.04")


def test_every_readme_number_is_in_an_artifact():
    readme = Path("README.md").read_text(encoding="utf-8")
    # Headline table rows only.
    wanted = [
        "0/239", "129/239", "142/1163", "142/5973", "3339/3339", "3339/5973",
        "1.000000", "1/100", "0/800", "425/800", "11467/11470", "262/4026",
    ]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in Path("artifacts").rglob("*") if p.is_file() and p.suffix in {".md", ".json"})
    missing = [w for w in wanted if w in readme and w not in blob]
    assert not missing, missing


def test_no_spec_illustrative_figure_is_republished():
    readme = Path("README.md").read_text(encoding="utf-8")
    for fig in SPEC_FIGURES:
        assert fig not in readme, fig
    for path in Path("artifacts").rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".json", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "spec" in text.lower() and "example" in text.lower():
            continue
        for fig in SPEC_FIGURES:
            assert fig not in text, (path, fig)


def test_no_tbd_markers_remain():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "TBD-" not in text
