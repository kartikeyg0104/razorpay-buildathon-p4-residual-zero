"""Server-rendered inline SVG waterfall. Coordinates from integer paise; no client arithmetic."""

from __future__ import annotations

from residual_zero.models import BankCredit, ProofRecord
from residual_zero.money import format_rupees


def waterfall_svg(proof: ProofRecord, credit: BankCredit) -> str:
    width = 640
    row_h = 28
    height = 80 + row_h * (len(proof.lines) + 3)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" data-waterfall="1">',
        f'<text x="8" y="24">credit {format_rupees(credit.amount_paise)}</text>',
    ]
    y = 48
    running = 0
    for line in proof.lines:
        running += line.amount_paise
        parts.append(
            f'<text x="8" y="{y}" data-paise="{line.amount_paise}">{line.label} {format_rupees(line.amount_paise)}</text>'
        )
        y += row_h
    parts.append(f'<text x="8" y="{y}" data-residual="{proof.residual_paise}">residual {format_rupees(proof.residual_paise)}</text>')
    parts.append("</svg>")
    return "".join(parts)
