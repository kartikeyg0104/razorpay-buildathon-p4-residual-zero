"""Server-rendered inline SVG waterfall. Coordinates from integer paise; no client arithmetic."""

from __future__ import annotations

from residual_zero.models import BankCredit, ProofRecord
from residual_zero.money import format_rupees

_FILL = {
    "PAYMENT": "#5dffc2",
    "REPRESENTMENT": "#5dffc2",
    "RESERVE_RELEASE": "#7ee0a8",
    "REFUND": "#ff6b7a",
    "CHARGEBACK": "#ff4d6d",
    "FEE": "#f0b429",
    "BANK_CHARGE": "#d4a017",
    "TAX_GST": "#7aa2ff",
    "TAX_WITHHOLDING": "#c084fc",
    "RESERVE_HOLD": "#fb923c",
    "ADJUSTMENT": "#94a3b8",
}


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _x(value: int, lo: int, span: int, left: int, width: int) -> int:
    return left + ((value - lo) * width) // span


def waterfall_svg(proof: ProofRecord, credit: BankCredit) -> str:
    left = 228
    plot = 640
    row_h = 34
    n_rows = len(proof.lines) + 2
    height = 64 + row_h * n_rows
    width = 920

    running = 0
    points = [0]
    for line in proof.lines:
        running += line.amount_paise
        points.append(running)
    points.append(running + proof.residual_paise)
    lo = min(points)
    hi = max(points)
    if credit.amount_paise > hi:
        hi = credit.amount_paise
    if credit.amount_paise < lo:
        lo = credit.amount_paise
    span = hi - lo
    if span <= 0:
        span = 1

    def x_of(value: int) -> int:
        return _x(value, lo, span, left, plot)

    x0_axis = x_of(0)
    x_credit = x_of(credit.amount_paise)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-waterfall="1" role="img" aria-label="decomposition waterfall">',
        f'<rect class="wf-bg" x="0" y="0" width="{width}" height="{height}" rx="16"/>',
        f'<line class="wf-axis" x1="{x0_axis}" y1="36" x2="{x0_axis}" y2="{height - 18}"/>',
        f'<line class="wf-target" x1="{x_credit}" y1="36" x2="{x_credit}" y2="{height - 18}"/>',
        f'<text class="wf-caption" x="{x0_axis}" y="24">0</text>',
        f'<text class="wf-caption" x="{x_credit}" y="24">credit {_esc(format_rupees(credit.amount_paise))}</text>',
    ]

    y = 48
    parts.append(
        f'<text class="wf-label" x="16" y="{y + 18}">credit</text>'
        f'<rect class="wf-credit" x="{min(x0_axis, x_credit)}" y="{y + 8}" width="{max(2, abs(x_credit - x0_axis))}" height="16" rx="3"/>'
        f'<text class="wf-amt" x="{left + plot + 12}" y="{y + 20}">{_esc(format_rupees(credit.amount_paise))}</text>'
    )
    y += row_h

    cursor = 0
    prev_end = x0_axis
    for i, line in enumerate(proof.lines):
        start = cursor
        cursor += line.amount_paise
        xa, xb = x_of(start), x_of(cursor)
        bar_x = xa if xa < xb else xb
        bar_w = xb - xa if xb > xa else xa - xb
        if line.amount_paise != 0 and bar_w < 2:
            bar_w = 2
        fill = _FILL.get(line.label, "#e2e8f0")
        cls = "wf-in" if line.amount_paise > 0 else "wf-out"
        parts.append(
            f'<line class="wf-join" x1="{prev_end}" y1="{y - 8}" x2="{xa}" y2="{y + 16}"/>'
            f'<text class="wf-label" x="16" y="{y + 18}">{_esc(line.label)}</text>'
            f'<rect class="{cls}" x="{bar_x}" y="{y + 7}" width="{bar_w}" height="18" rx="4" fill="{fill}" style="animation-delay: {i * 40}ms" data-paise="{line.amount_paise}"/>'
            f'<text class="wf-amt" x="{left + plot + 12}" y="{y + 20}">{_esc(format_rupees(line.amount_paise))}</text>'
        )
        prev_end = xb
        y += row_h

    xa, xb = x_of(cursor), x_of(cursor + proof.residual_paise)
    bar_x = xa if xa < xb else xb
    bar_w = xb - xa if xb > xa else xa - xb
    if proof.residual_paise != 0 and bar_w < 2:
        bar_w = 2
    if proof.residual_paise == 0:
        bar_w = 8
        bar_x = xa - 4
    parts.append(
        f'<text class="wf-label" x="16" y="{y + 18}">residual</text>'
        f'<rect class="wf-residual" x="{bar_x}" y="{y + 7}" width="{max(bar_w, 8)}" height="18" rx="4" data-residual="{proof.residual_paise}"/>'
        f'<text class="wf-amt wf-amt-zero" x="{left + plot + 12}" y="{y + 20}">{_esc(format_rupees(proof.residual_paise))}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
