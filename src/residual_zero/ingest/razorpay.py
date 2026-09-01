"""Razorpay test-mode adapter. Read-only. Cuttable via config enabled: false."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Mapping

from residual_zero.models import BankCredit, Kind, LedgerItem


class RazorpayTestModeAdapter:
    """Holds a read-only credential. Never writes anything anywhere."""

    def __init__(self, key_id: str, key_secret: str, enabled: bool) -> None:
        self.key_id = key_id
        self._secret = key_secret
        self.enabled = enabled
        self._seen_events: set[str] = set()

    def fetch_credits(self, window: tuple[date, date]) -> tuple[BankCredit, ...]:
        if not self.enabled:
            return ()
        return ()

    def fetch_items(self, window: tuple[date, date]) -> tuple[LedgerItem, ...]:
        if not self.enabled:
            return ()
        return ()

    def normalise_webhook(self, event: Mapping[str, Any]) -> tuple[str, LedgerItem | None]:
        event_id = str(event.get("event_id") or event.get("id") or "")
        if not event_id:
            raise ValueError("webhook missing event id")
        if event_id in self._seen_events:
            return event_id, None
        self._seen_events.add(event_id)
        return event_id, None


class ReconRow:
    """One row of GET /v1/settlements/recon/combined, already in integer paise."""

    __slots__ = ("settlement_id", "item_id", "kind", "amount_paise", "type_raw")

    def __init__(
        self, settlement_id: str, item_id: str, kind: Kind, amount_paise: int, type_raw: str,
    ) -> None:
        self.settlement_id = settlement_id
        self.item_id = item_id
        self.kind = kind
        self.amount_paise = amount_paise
        self.type_raw = type_raw


_RECON_KIND = {
    "payment": Kind.PAYMENT,
    "refund": Kind.REFUND,
    "fee": Kind.FEE,
    "recon_fee": Kind.FEE,
    "tax": Kind.TAX_GST,
    "recon_tax": Kind.TAX_GST,
    "adjustment": Kind.ADJUSTMENT,
    "transfer": Kind.ADJUSTMENT,
    "chargeback": Kind.CHARGEBACK,
    "reserve": Kind.RESERVE_HOLD,
}

# Official Razorpay MCP tools we will ingest. Everything else is a different product.
MCP_RECON_TOOL = "fetch_settlement_recon_details"
MCP_SETTLEMENT_TOOLS = frozenset(
    {
        "fetch_all_settlements",
        "fetch_settlement_with_id",
        "fetch_all_instant_settlements",
        "fetch_instant_settlement_with_id",
        MCP_RECON_TOOL,
    }
)


def unwrap_mcp_tool_result(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept raw recon JSON or an MCP tool envelope. Never fetches."""
    if isinstance(payload.get("items"), list):
        return payload
    content = payload.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            try:
                inner = json.loads(first["text"])
            except json.JSONDecodeError as exc:
                raise ValueError("MCP content text is not JSON") from exc
            if isinstance(inner, dict):
                return unwrap_mcp_tool_result(inner)
    for key in ("result", "data", "output"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            return unwrap_mcp_tool_result(inner)
    return payload


def _reject_wrong_mcp_tool(payload: Mapping[str, Any]) -> None:
    name = str(payload.get("tool") or payload.get("name") or payload.get("toolName") or "")
    if name and name not in MCP_SETTLEMENT_TOOLS and name != MCP_RECON_TOOL:
        raise ValueError(
            f"MCP tool {name!r} is not recon. Residual Zero only ingests "
            f"{MCP_RECON_TOOL} (GET /v1/settlements/recon/combined)."
        )
    if name in {
        "fetch_all_settlements",
        "fetch_settlement_with_id",
        "fetch_all_instant_settlements",
        "fetch_instant_settlement_with_id",
    }:
        raise ValueError(
            f"{name} is a settlement list/detail, not a recon report. "
            f"Call {MCP_RECON_TOOL}."
        )
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        first = items[0]
        if first.get("entity") == "settlement" and "entity_type" not in first and "type" not in first:
            raise ValueError(
                "this is fetch_all_settlements. Paste fetch_settlement_recon_details instead."
            )


def parse_recon_combined(payload: Mapping[str, Any]) -> tuple[ReconRow, ...]:
    """Read-only parse. Never fetches. Amounts must already be integer paise.

    Accepts the Razorpay recon/combined body, or the MCP envelope for
    ``fetch_settlement_recon_details``. Does not call mcp.razorpay.com.
    """
    if not isinstance(payload, dict):
        raise ValueError("recon payload must be a JSON object")
    _reject_wrong_mcp_tool(payload)
    payload = unwrap_mcp_tool_result(payload)
    _reject_wrong_mcp_tool(payload)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("recon payload missing items list")
    out: list[ReconRow] = []
    for i, row in enumerate(raw_items):
        if not isinstance(row, dict):
            raise ValueError(f"items[{i}] is not an object")
        type_raw = str(row.get("entity_type") or row.get("type") or "").strip().casefold()
        kind = _RECON_KIND.get(type_raw)
        if kind is None:
            raise ValueError(f"items[{i}]: unknown entity_type {type_raw!r}")
        amount = row.get("amount")
        if type(amount) is not int:
            raise ValueError(f"items[{i}]: amount must be integer paise, not {type(amount).__name__}")
        settlement = str(row.get("settlement_id") or "").strip()
        item_id = str(row.get("entity_id") or row.get("id") or "").strip()
        if not settlement or not item_id:
            raise ValueError(f"items[{i}]: settlement_id and entity_id required")
        out.append(ReconRow(settlement, item_id, kind, amount, type_raw))
    return tuple(out)
