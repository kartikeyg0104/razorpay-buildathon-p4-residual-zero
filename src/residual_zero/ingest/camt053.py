"""F45 ISO 20022 CAMT.053 adapter."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from residual_zero.ingest import IngestError
from residual_zero.models import BankCredit
from residual_zero.money import format_rupees
from residual_zero.normalise import normalise_narration, parse_rupee_display

NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"


def _etree():
    try:
        from lxml import etree as tree  # type: ignore
        return tree, True
    except ImportError:
        import xml.etree.ElementTree as tree
        return tree, False


def render_camt053(credits: tuple[BankCredit, ...], account_id: str) -> bytes:
    """Render a minimal statement. Opening balance 0; closing = sum of credits."""
    etree, _ = _etree()
    total = sum(c.amount_paise for c in credits)
    days = [c.value_date for c in credits] or [date(2025, 1, 6)]
    opening = 0
    lines = [
        f'<Document xmlns="{NS}">',
        "  <BkToCstmrStmt><Stmt>",
        f"    <Id>{account_id}</Id>",
        "    <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>"
        f'<Amt Ccy="INR">{_amt(opening)}</Amt></Bal>',
        "    <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>"
        f'<Amt Ccy="INR">{_amt(total)}</Amt></Bal>',
    ]
    for credit in credits:
        lines.append(_entry(credit))
    lines.append("  </Stmt></BkToCstmrStmt></Document>")
    text = "\n".join(lines)
    return text.encode("utf-8")


def _amt(paise: int) -> str:
    return format_rupees(paise).replace(",", "")


def _entry(credit: BankCredit) -> str:
    return (
        "    <Ntry>"
        f'<Amt Ccy="{credit.currency}">{_amt(credit.amount_paise)}</Amt>'
        "<CdtDbtInd>CRDT</CdtDbtInd>"
        f"<ValDt><Dt>{credit.value_date.isoformat()}</Dt></ValDt>"
        "<NtryDtls><TxDtls>"
        f"<Refs><EndToEndId>{_xml(credit.id)}</EndToEndId>"
        f"<AcctSvcrRef>{_xml(credit.utr or credit.id)}</AcctSvcrRef></Refs>"
        f"<RmtInf><Ustrd>{_xml(credit.narration_raw)}</Ustrd></RmtInf>"
        f"<AddtlTxInf>{_xml(credit.account_id)}</AddtlTxInf>"
        "</TxDtls></NtryDtls></Ntry>"
    )


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_camt053(payload: bytes, *, path: str = "statement.xml") -> tuple[BankCredit, ...]:
    etree, is_lxml = _etree()
    try:
        if is_lxml:
            root = etree.fromstring(payload)
        else:
            root = etree.fromstring(payload)
    except Exception as exc:
        raise IngestError("truncated or malformed XML", path=path, element="Document") from exc
    ns = {"c": NS}

    def findall(node, xpath: str):
        if is_lxml:
            return node.findall(xpath, namespaces=ns)
        # ElementTree: local-name fallback
        return _findall_local(node, xpath)

    entries = findall(root, ".//{urn:iso:std:iso:20022:tech:xsd:camt.053.001.08}Ntry")
    if not entries:
        entries = _findall_local(root, "Ntry")
    credits: list[BankCredit] = []
    for idx, entry in enumerate(entries, start=1):
        try:
            credits.append(_ntry_to_credit(entry, path, idx))
        except IngestError:
            raise
        except Exception as exc:
            raise IngestError(str(exc), path=path, element=f"Ntry[{idx}]") from exc
    _check_balances(root, credits, path)
    return tuple(credits)


def _findall_local(node, local: str):
    found = []
    tag_end = local.split("}")[-1]
    for el in node.iter():
        name = el.tag.split("}")[-1]
        if name == tag_end:
            found.append(el)
    return found


def _text(node, local: str) -> str | None:
    for el in node.iter():
        if el.tag.split("}")[-1] == local:
            if el.text:
                return el.text
    return None


def _ntry_to_credit(entry, path: str, idx: int) -> BankCredit:
    amt_el = None
    ccy = "INR"
    for el in entry.iter():
        if el.tag.split("}")[-1] == "Amt":
            amt_el = el
            ccy = el.attrib.get("Ccy", "INR")
            break
    if amt_el is None or not (amt_el.text or "").strip():
        raise IngestError("CAMT entry missing amount", path=path, element=f"Ntry[{idx}]/Amt")
    ind = _text(entry, "CdtDbtInd") or "CRDT"
    if ind != "CRDT":
        raise IngestError(f"unsupported CdtDbtInd {ind}", path=path, element=f"Ntry[{idx}]")
    day_s = _text(entry, "Dt")
    if not day_s:
        raise IngestError("missing ValDt", path=path, element=f"Ntry[{idx}]/ValDt")
    cid = _text(entry, "EndToEndId")
    if not cid:
        raise IngestError("missing EndToEndId", path=path, element=f"Ntry[{idx}]")
    narration = _text(entry, "Ustrd") or ""
    account = _text(entry, "AddtlTxInf") or "acc_00"
    utr = _text(entry, "AcctSvcrRef")
    amount_paise = parse_rupee_display(amt_el.text.strip())
    return BankCredit(
        id=cid,
        amount_paise=amount_paise,
        value_date=date.fromisoformat(day_s),
        account_id=account,
        currency=ccy,
        narration_raw=narration,
        narration_norm=normalise_narration(narration),
        utr=utr,
    )


def _check_balances(root, credits: list[BankCredit], path: str) -> None:
    bals = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "Bal":
            cd = None
            amt = None
            for child in el.iter():
                loc = child.tag.split("}")[-1]
                if loc == "Cd" and child.text:
                    cd = child.text
                if loc == "Amt" and child.text:
                    amt = parse_rupee_display(child.text.strip())
            if cd in {"OPBD", "CLBD"} and amt is not None:
                bals.append((cd, amt))
    opening = next((a for c, a in bals if c == "OPBD"), 0)
    closing = next((a for c, a in bals if c == "CLBD"), None)
    if closing is None:
        return
    got = opening + sum(c.amount_paise for c in credits)
    if got != closing:
        raise IngestError(
            f"closing balance {closing} != opening+credits {got}",
            path=path,
            element="Bal/CLBD",
        )


def load_camt053(path: Path) -> tuple[BankCredit, ...]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise IngestError(str(exc), path=str(path)) from exc
    return parse_camt053(payload, path=str(path))
