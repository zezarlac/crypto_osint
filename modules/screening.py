"""
modules/screening.py — CryptoWalletOSINT
Screens wallet addresses against a local sanctions/mixer watchlist.

Data source: data/sanctions_addresses.json — a small CURATED SAMPLE
built from official U.S. Treasury OFAC SDN press releases. This is
NOT the complete or live-updated SDN list. For full compliance
screening use the official OFAC source or a commercial provider.
"""

import json
import os
from typing import Optional

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sanctions_addresses.json"
)


class Screener:
    def __init__(self, data_path: str = None):
        self.data_path = data_path or _DATA_PATH
        self._index = {}   # normalized address -> entry dict
        self._meta  = {}
        self._load()

    def _load(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._meta = data.get("meta", {})
            for entry in data.get("entries", []):
                addr = entry.get("address", "")
                # ETH addresses are case-insensitive; BTC/TRX are case-sensitive
                key = addr.lower() if addr.startswith("0x") else addr
                self._index[key] = entry
        except Exception as e:
            print(f"  [screening] ⚠ Could not load watchlist: {e}")

    # ── Public API ───────────────────────────────────────────

    def check(self, address: str) -> Optional[dict]:
        """Return the matching watchlist entry for `address`, or None."""
        if not address:
            return None
        key = address.lower() if address.startswith("0x") else address
        return self._index.get(key)

    def check_many(self, addresses) -> dict:
        """Screen a list/set of addresses. Returns {address: entry} for matches only."""
        hits = {}
        for addr in addresses:
            match = self.check(addr)
            if match:
                hits[addr] = match
        return hits

    def is_mixer(self, address: str) -> bool:
        """Convenience check: is this address a known mixer?"""
        match = self.check(address)
        return bool(match and "mixer" in match.get("category", []))

    def stats(self) -> dict:
        """Return basic info about the loaded dataset."""
        return {
            "total_entries": len(self._index),
            "last_updated":  self._meta.get("last_updated", "unknown"),
            "source":        self._meta.get("source", ""),
            "disclaimer":    self._meta.get("disclaimer", ""),
        }
