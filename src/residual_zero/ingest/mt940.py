"""F45 MT940 adapter. :86: is the truncated narration field modelled as class 16 in DATA.md."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from residual_zero.ingest import IngestError
from residual_zero.models import BankCredit
from residual_zero.money import format_rupees
from residual_zero.normalise import normalise_narration, parse_rupee_display

_MAX_86 = 35  # class-16 truncation width


def render_mt940(credits: tuple[BankCredit, ...], account_id: str) -> str:
    if not credits:
        start = date(2025, 1, 6)
        end = start
        opening = 0
        closing = 0
    else:
        start = min(c.value_date for c in credits)
        end = max(c.value_date for c in credits)
        opening = 0
        closing = sum(c.amount_paise for c in credits)
    lines = [
        ":20:START",
        f":25:{account_id}",
        ":28C:1",
        f":60F:C{_yyMMdd(start)}INR{_swift_amt(opening)}",
    ]
    for credit in credits:
        lines.append(_tag61(credit))
        payload = (
            f"ID={credit.id}|ACC={credit.account_id}|UTR={credit.utr or ''}|"
            f"NARR={credit.narration_raw}"
        )
        lines.append(f":86:{payload[:_MAX_86]}")
        leftover = payload[_MAX_86:]
        while leftover:
            lines.append(leftover[:_MAX_86])
            leftover = leftover[_MAX_86:]
    lines.append(f":62F:C{_yyMMdd(end)}INR{_swift_amt(closing)}")
    return "\n".join(lines) + "\n"


def _yyMMdd(day: date) -> str:
    return day.strftime("%y%m%d")


def _swift_amt(paise: int) -> str:
    rupees = format_rupees(paise).replace(",", "")
    if "." in rupees:
        whole, frac = rupees.split(".", 1)
        return f"{whole},{frac}"
    return rupees + ",00"


def _tag61(credit: BankCredit) -> str:
    yymmdd = _yyMMdd(credit.value_date)
    return f":61:{yymmdd}{yymmdd[2:]}C{_swift_amt(credit.amount_paise)}NTRFNONREF"


def parse_mt940(text: str, *, path: str = "statement.sta") -> tuple[BankCredit, ...]:
    raw_lines = text.splitlines()
    if not raw_lines:
        raise IngestError("empty MT940", path=path, line=1)
    credits: list[BankCredit] = []
    i = 0
    current_61: str | None = None
    current_86: list[str] = []
    account_id = "acc_00"

    def flush() -> None:
        nonlocal current_61, current_86
        if current_61 is None:
            current_86 = []
            return
        credits.append(_parse_pair(current_61, "".join(current_86), account_id, path, len(credits) + 1))
        current_61 = None
        current_86 = []

    while i < len(raw_lines):
        line = raw_lines[i]
        if line.startswith(":25:"):
            account_id = line[4:].strip() or account_id
        elif line.startswith(":61:"):
            flush()
            current_61 = line[4:]
        elif line.startswith(":86:"):
            current_86.append(line[4:])
        elif current_61 is not None and current_86 and not line.startswith(":"):
            current_86.append(line)
        elif line.startswith(":62"):
            flush()
        i += 1
    flush()
    return tuple(credits)


def _parse_pair(tag61: str, tag86: str, account_id: str, path: str, idx: int) -> BankCredit:
    if len(tag61) < 11:
        raise IngestError("MT940 :61: too short", path=path, line=idx, element=":61:")
    try:
        value_date = date(2000 + int(tag61[0:2]), int(tag61[2:4]), int(tag61[4:6]))
    except ValueError as exc:
        raise IngestError("unparseable :61: date", path=path, element=":61:") from exc
    rest = tag61[10:]
    if not rest or rest[0] not in {"C", "D"}:
        # ddmmyy + C/D: after 6+4 = 10 chars we should see C
        # :61:YYMMDDMMDDC...  6+4=10
        pass
    sign_at = None
    for j, ch in enumerate(tag61):
        if ch in {"C", "D"} and j >= 6:
            sign_at = j
            break
    if sign_at is None:
        raise IngestError("missing C/D indicator", path=path, element=":61:")
    if tag61[sign_at] != "C":
        raise IngestError("debit :61: not a bank credit", path=path, element=":61:")
    amt_s = tag61[sign_at + 1 :]
    amt_s = amt_s.split("N", 1)[0]
    amt_s = amt_s.replace(",", ".")
    try:
        amount_paise = parse_rupee_display(amt_s)
    except Exception as exc:
        raise IngestError("unparseable :61: amount", path=path, element=":61:") from exc
    cid = _extract(tag86, "ID") or f"mt940_{idx}"
    acc = _extract(tag86, "ACC") or account_id
    utr = _extract(tag86, "UTR") or None
    if utr == "":
        utr = None
    narration = ""
    if "NARR=" in tag86:
        narration = tag86.split("NARR=", 1)[1]
    return BankCredit(
        id=cid,
        amount_paise=amount_paise,
        value_date=value_date,
        account_id=acc,
        currency="INR",
        narration_raw=narration,
        narration_norm=normalise_narration(narration),
        utr=utr,
    )


def _extract(blob: str, key: str) -> str | None:
    token = f"{key}="
    # first field has no leading pipe
    if blob.startswith(token):
        rest = blob[len(token):]
        return rest.split("|", 1)[0]
    token = f"|{key}="
    if token not in blob:
        return None
    rest = blob.split(token, 1)[1]
    return rest.split("|", 1)[0]


def load_mt940(path: Path) -> tuple[BankCredit, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError("wrong encoding", path=str(path), line=1) from exc
    except OSError as exc:
        raise IngestError(str(exc), path=str(path)) from exc
    return parse_mt940(text, path=str(path))
