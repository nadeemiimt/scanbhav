"""Bank / UPI payout details for sell-all proceeds (local store)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

PAYOUT_PATH = BASE_DIR / "data" / "payout_account.json"


def load_payout_account() -> dict[str, Any]:
    if not PAYOUT_PATH.exists():
        return {}
    try:
        return json.loads(PAYOUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_payout_account(payload: dict[str, Any]) -> dict[str, Any]:
    clean = {
        "account_holder": (payload.get("account_holder") or "").strip(),
        "bank_name": (payload.get("bank_name") or "").strip(),
        "account_number": (payload.get("account_number") or "").strip(),
        "ifsc": (payload.get("ifsc") or "").strip().upper(),
        "upi_id": (payload.get("upi_id") or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if clean["ifsc"] and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", clean["ifsc"]):
        raise ValueError("IFSC format looks invalid (e.g. HDFC0001234).")
    PAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAYOUT_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    # Mask account number in response
    masked = {**clean}
    if masked.get("account_number") and len(masked["account_number"]) > 4:
        masked["account_number_masked"] = "*" * (len(masked["account_number"]) - 4) + masked["account_number"][-4:]
    return masked


def payout_summary() -> dict[str, Any]:
    acc = load_payout_account()
    if not acc:
        return {"configured": False, "message": "Add bank account to see expected transfer destination."}
    masked = {**acc}
    num = acc.get("account_number") or ""
    if len(num) > 4:
        masked["account_number_masked"] = "*" * (len(num) - 4) + num[-4:]
        masked.pop("account_number", None)
    return {"configured": True, "account": masked}
