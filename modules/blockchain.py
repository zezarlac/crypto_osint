"""
modules/blockchain.py — CryptoWalletOSINT
Fetches wallet data from public blockchain APIs.

APIs used (all free):
  Bitcoin   → blockchain.info      (no key needed)
  Ethereum  → Etherscan API V2     (free key at etherscan.io)
  Tron      → Tronscan API         (no key needed)
  LTC/DOGE  → Blockchair API       (no key, rate-limited)
"""

import time
import requests
from config import Config


class BlockchainFetcher:
    def __init__(self):
        self.cfg = Config()
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (CryptoWalletOSINT/1.0 Educational Research)"
        })

    # ── Public entry point ────────────────────────────────────

    def fetch(self, address: str, chain: str, max_tx: int = 50) -> dict:
        """Dispatch to the correct chain fetcher."""
        dispatch = {
            "bitcoin":  self._fetch_bitcoin,
            "ethereum": self._fetch_ethereum,
            "tron":     self._fetch_tron,
            "litecoin": lambda a, n: self._fetch_blockchair(a, n, "litecoin"),
            "dogecoin": lambda a, n: self._fetch_blockchair(a, n, "dogecoin"),
        }
        fn = dispatch.get(chain)
        return fn(address, max_tx) if fn else {"error": f"Unsupported chain: {chain}"}

    # ── Bitcoin ───────────────────────────────────────────────

    def _fetch_bitcoin(self, address: str, max_tx: int) -> dict:
        """blockchain.info — no API key required."""
        try:
            r = self.s.get(
                f"https://blockchain.info/rawaddr/{address}",
                params={"limit": max_tx},
                timeout=self.cfg.TIMEOUT
            )
            r.raise_for_status()
            raw = r.json()

            transactions = []
            for tx in raw.get("txs", []):
                inputs = [
                    inp.get("prev_out", {}).get("addr", "coinbase")
                    for inp in tx.get("inputs", [])
                ]
                outputs = [
                    {
                        "address":   o.get("addr", "unknown"),
                        "value_btc": o.get("value", 0) / 1e8,
                        "spent":     o.get("spent", False),
                    }
                    for o in tx.get("out", [])
                ]
                transactions.append({
                    "txid":      tx.get("hash"),
                    "time":      tx.get("time"),
                    "block":     tx.get("block_height"),
                    "inputs":    inputs,
                    "outputs":   outputs,
                    "fee_btc":   tx.get("fee", 0) / 1e8,
                    "confirmed": tx.get("block_height") is not None,
                })

            return {
                "address":            address,
                "chain":              "bitcoin",
                "balance_btc":        raw.get("final_balance", 0) / 1e8,
                "total_received_btc": raw.get("total_received", 0) / 1e8,
                "total_sent_btc":     raw.get("total_sent", 0) / 1e8,
                "tx_count":           raw.get("n_tx", 0),
                "transactions":       transactions,
                "label":              self._btc_label(address),
            }
        except Exception as e:
            return {"error": str(e), "address": address, "chain": "bitcoin"}

    # ── Ethereum (Etherscan API V2) ───────────────────────────

    # V1 endpoint (https://api.etherscan.io/api) was deprecated in 2024.
    # V2 requires the same key but a different URL and a mandatory chainid param.
    _ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
    _ETH_CHAIN_ID   = 1   # 1 = Ethereum mainnet

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Parse int from API result — returns default for non-numeric strings."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _eth_params(self, extra: dict) -> dict:
        """Shared base params for every Etherscan V2 call."""
        return {
            "chainid": self._ETH_CHAIN_ID,
            "apikey":  self.cfg.ETHERSCAN_API_KEY,
            **extra,
        }

    def _fetch_ethereum(self, address: str, max_tx: int) -> dict:
        """Etherscan API V2 — free key required (etherscan.io/register)."""
        base = self._ETHERSCAN_BASE
        try:
            # ── Balance ──────────────────────────────────────
            bal_r = self.s.get(base, params=self._eth_params({
                "module": "account", "action": "balance",
                "address": address, "tag": "latest",
            }), timeout=self.cfg.TIMEOUT).json()

            balance_eth = self._safe_int(bal_r.get("result", "0")) / 1e18
            time.sleep(self.cfg.RATE_DELAY)

            # ── Normal transactions ───────────────────────────
            txs_r = self.s.get(base, params=self._eth_params({
                "module": "account", "action": "txlist",
                "address": address, "startblock": 0,
                "endblock": 99999999, "page": 1,
                "offset": max_tx, "sort": "desc",
            }), timeout=self.cfg.TIMEOUT).json()
            time.sleep(self.cfg.RATE_DELAY)

            transactions = []
            result_list = txs_r.get("result", [])
            if isinstance(result_list, list):
                for tx in result_list:
                    if not isinstance(tx, dict):
                        continue
                    transactions.append({
                        "txid":      tx.get("hash"),
                        "time":      self._safe_int(tx.get("timeStamp", 0)),
                        "block":     tx.get("blockNumber"),
                        "from":      tx.get("from", ""),
                        "to":        tx.get("to", ""),
                        "value_eth": self._safe_int(tx.get("value", 0)) / 1e18,
                        "gas_used":  tx.get("gasUsed"),
                        "confirmed": tx.get("txreceipt_status") == "1",
                        "is_error":  tx.get("isError") == "1",
                    })

            return {
                "address":      address,
                "chain":        "ethereum",
                "balance_eth":  balance_eth,
                "tx_count":     len(transactions),
                "transactions": transactions,
                "label":        self._eth_label(address),
            }
        except Exception as e:
            return {"error": str(e), "address": address, "chain": "ethereum"}

    # ── Tron ──────────────────────────────────────────────────

    def _fetch_tron(self, address: str, max_tx: int) -> dict:
        """Tronscan public API — no key required."""
        try:
            acc = self.s.get(
                "https://apilist.tronscanapi.com/api/accountv2",
                params={"address": address}, timeout=self.cfg.TIMEOUT
            ).json()
            time.sleep(self.cfg.RATE_DELAY)

            txs_r = self.s.get(
                "https://apilist.tronscanapi.com/api/transaction",
                params={
                    "sort": "-timestamp", "count": "true",
                    "limit": max_tx, "start": 0, "address": address
                }, timeout=self.cfg.TIMEOUT
            ).json()

            transactions = [
                {
                    "txid":      tx.get("hash"),
                    "time":      tx.get("timestamp"),
                    "from":      tx.get("ownerAddress"),
                    "to":        tx.get("toAddress"),
                    "value_trx": tx.get("amount", 0) / 1e6,
                    "confirmed": tx.get("confirmed", False),
                }
                for tx in txs_r.get("data", [])
            ]

            return {
                "address":      address,
                "chain":        "tron",
                "balance_trx":  acc.get("balance", 0) / 1e6,
                "tx_count":     acc.get("transactions_count", 0),
                "transactions": transactions,
                "label":        acc.get("addressTag", ""),
            }
        except Exception as e:
            return {"error": str(e), "address": address, "chain": "tron"}

    # ── LTC / DOGE via Blockchair ─────────────────────────────

    def _fetch_blockchair(self, address: str, max_tx: int, chain: str) -> dict:
        """Blockchair public API — no key required (rate-limited)."""
        try:
            r = self.s.get(
                f"https://api.blockchair.com/{chain}/dashboards/address/{address}",
                timeout=self.cfg.TIMEOUT
            )
            r.raise_for_status()
            data = r.json().get("data", {}).get(address, {})
            info = data.get("address", {})
            txids = data.get("transactions", [])[:max_tx]

            return {
                "address":      address,
                "chain":        chain,
                "balance":      info.get("balance", 0),
                "received":     info.get("received", 0),
                "spent":        info.get("spent", 0),
                "tx_count":     info.get("transaction_count", 0),
                "transactions": [{"txid": t} for t in txids],
                "label":        info.get("type", ""),
            }
        except Exception as e:
            return {"error": str(e), "address": address, "chain": chain}

    # ── Entity label helpers ──────────────────────────────────

    def _btc_label(self, address: str) -> str:
        """Check Blockchair for a known BTC address label."""
        try:
            r = self.s.get(
                f"https://api.blockchair.com/bitcoin/dashboards/address/{address}",
                timeout=10
            ).json()
            return (
                r.get("data", {})
                 .get(address, {})
                 .get("address", {})
                 .get("type", "")
            )
        except Exception:
            return ""

    def _eth_label(self, address: str) -> str:
        """Check Etherscan V2 for a contract name label."""
        try:
            r = self.s.get(self._ETHERSCAN_BASE, params=self._eth_params({
                "module": "contract", "action": "getsourcecode",
                "address": address,
            }), timeout=10).json()
            result = r.get("result", [{}])
            if result and isinstance(result, list):
                name = result[0].get("ContractName", "")
                return f"Contract: {name}" if name else ""
            return ""
        except Exception:
            return ""
