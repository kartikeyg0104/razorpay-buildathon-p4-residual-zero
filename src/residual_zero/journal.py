"""F40 double-entry journal export. A file the user imports; no credentials (spec §1.3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import BankCredit, Kind, LedgerItem
from residual_zero.money import format_rupees

_STRICT = ConfigDict(frozen=True, extra="forbid")


class AccountRef(BaseModel):
    model_config = _STRICT
    code: str
    name: str


class KindMap(BaseModel):
    model_config = _STRICT
    debit: AccountRef | None = None
    credit: AccountRef | None = None


class ChartOfAccounts(BaseModel):
    model_config = _STRICT
    bank_control: AccountRef
    unreconciled: AccountRef
    kind_map: dict[str, KindMap]


class JournalLine(BaseModel):
    model_config = _STRICT
    date: date
    account_code: str
    account_name: str
    debit_paise: int = Field(ge=0)
    credit_paise: int = Field(ge=0)
    narration: str
    reference: str


def load_chart(path: Path | None = None) -> ChartOfAccounts:
    if path is None:
        path = Path("config").joinpath("chart_of_accounts.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ChartOfAccounts.model_validate(raw)


def _line(day: date, acct: AccountRef, debit: int, credit: int, narration: str, ref: str) -> JournalLine:
    if debit < 0 or credit < 0:
        raise ValueError("journal amounts are unsigned paise; sign is the debit/credit column")
    if (debit == 0) == (credit == 0):
        raise ValueError("exactly one of debit or credit must be non-zero")
    return JournalLine(
        date=day,
        account_code=acct.code,
        account_name=acct.name,
        debit_paise=debit,
        credit_paise=credit,
        narration=narration,
        reference=ref,
    )


def _kind_lines(
    chart: ChartOfAccounts,
    item: LedgerItem,
    day: date,
    ref: str,
) -> tuple[JournalLine, ...]:
    mapping = chart.kind_map.get(item.kind.value)
    if mapping is None:
        raise ValueError(f"no chart mapping for kind {item.kind.value}")
    amt = item.amount_paise if item.amount_paise > 0 else -item.amount_paise
    if item.kind == Kind.ADJUSTMENT:
        if item.amount_paise < 0:
            acct = mapping.debit or mapping.credit
        else:
            acct = mapping.credit or mapping.debit
        if acct is None:
            raise ValueError("ADJUSTMENT mapping needs debit or credit")
        if item.amount_paise < 0:
            return (_line(day, acct, amt, 0, item.kind.value, ref),)
        return (_line(day, acct, 0, amt, item.kind.value, ref),)
    if item.amount_paise < 0:
        acct = mapping.debit
        if acct is None:
            raise ValueError(f"{item.kind.value} needs a debit account")
        return (_line(day, acct, amt, 0, item.kind.value, ref),)
    acct = mapping.credit
    if acct is None:
        raise ValueError(f"{item.kind.value} needs a credit account")
    return (_line(day, acct, 0, amt, item.kind.value, ref),)


def build_journal(
    credits: Sequence[BankCredit],
    ledger: Mapping[str, LedgerItem],
    cleared_members: Mapping[str, tuple[str, ...]],
    chart: ChartOfAccounts,
) -> tuple[JournalLine, ...]:
    """Every credit: Dr Bank. CLEARED: Cr/Dr member accounts. Else Cr suspense."""
    lines: list[JournalLine] = []
    for credit in credits:
        ref = credit.id
        day = credit.value_date
        lines.append(
            _line(day, chart.bank_control, credit.amount_paise, 0, "bank credit", ref)
        )
        members = cleared_members.get(credit.id)
        if not members:
            lines.append(
                _line(
                    day, chart.unreconciled, 0, credit.amount_paise,
                    "unreconciled", ref,
                )
            )
            continue
        member_sum = 0
        for item_id in members:
            item = ledger[item_id]
            member_sum += item.amount_paise
            lines.extend(_kind_lines(chart, item, day, ref))
        # Residual 0 is required of CLEARED; if members do not sum to the credit, refuse a plug.
        if member_sum != credit.amount_paise:
            raise ValueError(
                f"{credit.id}: member sum {member_sum} != credit {credit.amount_paise}; no plug"
            )
    return tuple(lines)


def trial_balance(lines: Sequence[JournalLine]) -> tuple[int, int]:
    return sum(l.debit_paise for l in lines), sum(l.credit_paise for l in lines)


def control_residual(lines: Sequence[JournalLine], credits: Sequence[BankCredit], bank_code: str) -> int:
    posted = sum(l.debit_paise - l.credit_paise for l in lines if l.account_code == bank_code)
    return posted - sum(c.amount_paise for c in credits)


def render_csv(lines: Sequence[JournalLine]) -> str:
    rows = ["date,account_code,account_name,debit_paise,credit_paise,narration,reference"]
    for line in lines:
        rows.append(
            f"{line.date.isoformat()},{line.account_code},{line.account_name},"
            f"{line.debit_paise},{line.credit_paise},{line.narration},{line.reference}"
        )
    return "\n".join(rows) + "\n"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _tally_amount(paise: int) -> str:
    """Major-unit string from format_rupees. No true division on money."""
    return format_rupees(paise).replace(",", "")


def render_tally_xml(lines: Sequence[JournalLine]) -> str:
    """Tally XML import of F40 journal lines. A file the user imports; no credentials."""
    grouped: dict[str, list[JournalLine]] = {}
    order: list[str] = []
    for line in lines:
        if line.reference not in grouped:
            order.append(line.reference)
            grouped[line.reference] = []
        grouped[line.reference].append(line)
    vouchers: list[str] = []
    for ref in order:
        chunk = grouped[ref]
        day = chunk[0].date.strftime("%Y%m%d")
        narration = _xml_escape(chunk[0].narration)
        entries: list[str] = []
        for line in chunk:
            if line.debit_paise:
                deemed = "Yes"
                amount = _tally_amount(-line.debit_paise)
            else:
                deemed = "No"
                amount = _tally_amount(line.credit_paise)
            entries.append(
                "      <ALLLEDGERENTRIES.LIST>\n"
                f"       <LEDGERNAME>{_xml_escape(line.account_name)}</LEDGERNAME>\n"
                f"       <ISDEEMEDPOSITIVE>{deemed}</ISDEEMEDPOSITIVE>\n"
                f"       <AMOUNT>{amount}</AMOUNT>\n"
                "      </ALLLEDGERENTRIES.LIST>"
            )
        vouchers.append(
            "    <TALLYMESSAGE>\n"
            "     <VOUCHER>\n"
            f"      <DATE>{day}</DATE>\n"
            "      <VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>\n"
            f"      <NARRATION>{narration}</NARRATION>\n"
            f"      <REFERENCE>{_xml_escape(ref)}</REFERENCE>\n"
            + "\n".join(entries)
            + "\n     </VOUCHER>\n"
            "    </TALLYMESSAGE>"
        )
    body = "\n".join(vouchers)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<ENVELOPE>\n"
        " <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>\n"
        " <BODY><IMPORTDATA><REQUESTDATA>\n"
        f"{body}\n"
        " </REQUESTDATA></IMPORTDATA></BODY>\n"
        "</ENVELOPE>\n"
    )


def write_journal(path: Path, lines: Sequence[JournalLine]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_csv(lines), encoding="utf-8")
