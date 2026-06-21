"""
modules/tracer.py — CryptoWalletOSINT
Multi-hop transaction tracer.

Follows funds beyond the first hop by fetching transaction data for
the addresses a wallet has interacted with, up to a configurable
depth (max 3). To stay fast and within free API rate limits, only
the highest-value counterparties are expanded at each hop.

Every newly discovered address is automatically screened against
the local sanctions/mixer watchlist (modules/screening.py).
"""

import time
from config import Config
from modules.blockchain import BlockchainFetcher
from modules.screening import Screener
from modules.utils import extract_edges

# Internal tuning — kept out of the CLI to stay simple.
DEFAULT_MAX_PER_HOP        = 6     # addresses expanded per hop
DEFAULT_MAX_TX_PER_ADDRESS = 15    # transactions fetched per address (hops 2+)


class MultiHopTracer:
    def __init__(self, fetcher: BlockchainFetcher = None,
                 max_per_hop: int = DEFAULT_MAX_PER_HOP,
                 max_tx_per_address: int = DEFAULT_MAX_TX_PER_ADDRESS):
        self.cfg                = Config()
        self.fetcher             = fetcher or BlockchainFetcher()
        self.screener            = Screener()
        self.max_per_hop         = max_per_hop
        self.max_tx_per_address  = max_tx_per_address

    # ── Public API ───────────────────────────────────────────

    def trace(self, address: str, chain: str, depth: int = 2,
              root_wallet_data: dict = None, progress_cb=None) -> dict:
        """
        Trace fund movements up to `depth` hops from `address`.
        `progress_cb(message)` is called with short status strings
        if provided (used by main.py to update the console).
        """
        depth = max(1, min(depth, 3))   # hard cap — protects free API quotas

        def _progress(msg):
            if progress_cb:
                progress_cb(msg)

        visited = {address}
        nodes   = {address: {"hop": 0, "label": "TARGET"}}
        edges   = []
        hop_counts = {}

        # ── Hop 1 — reuse already-fetched data when available ──
        wallet_data = root_wallet_data or self.fetcher.fetch(
            address, chain, max_tx=self.max_tx_per_address
        )
        hop1_edges = extract_edges(address, wallet_data, hop=1)
        edges.extend(hop1_edges)

        frontier = self._top_counterparties(hop1_edges, address, visited)
        hop_counts[1] = len(frontier)
        for addr in frontier:
            nodes[addr] = {"hop": 1}
            visited.add(addr)
        _progress(f"Hop 1: {len(frontier)} addresses discovered")

        # ── Hops 2..depth ──
        for hop in range(2, depth + 1):
            next_frontier = []
            for addr in frontier:
                time.sleep(self.cfg.RATE_DELAY)
                wd = self.fetcher.fetch(addr, chain, max_tx=self.max_tx_per_address)
                if "error" in wd:
                    continue
                nodes[addr]["balance"] = self._get_balance(wd, chain)
                nodes[addr]["label"]   = wd.get("label", "")

                hop_edges = extract_edges(addr, wd, hop=hop)
                edges.extend(hop_edges)

                for c in self._top_counterparties(hop_edges, addr, visited):
                    nodes[c] = {"hop": hop}
                    visited.add(c)
                    next_frontier.append(c)

            hop_counts[hop] = len(next_frontier)
            _progress(f"Hop {hop}: {len(next_frontier)} addresses discovered")
            frontier = next_frontier
            if not frontier:
                break

        # ── Screen every discovered address (local, no extra API cost) ──
        flagged = {}
        for addr in nodes:
            match = self.screener.check(addr)
            if match:
                nodes[addr]["flagged"] = match
                flagged[addr] = match

        return {
            "target":           address,
            "chain":            chain,
            "depth":            depth,
            "nodes":            nodes,
            "edges":            edges,
            "hop_counts":       hop_counts,
            "flagged":          flagged,
            "total_addresses":  len(nodes),
        }

    # ── Internal helpers ─────────────────────────────────────

    def _top_counterparties(self, edges: list, src_address: str, visited: set) -> list:
        """
        Rank counterparties by total transferred value and return the
        top N unvisited ones. This keeps the trace focused on the
        biggest fund movements instead of exploding combinatorially.
        """
        totals = {}
        for e in edges:
            other = e["to"] if e["from"] == src_address else e["from"]
            if not other or other == src_address or other in visited:
                continue
            totals[other] = totals.get(other, 0) + abs(e.get("value", 0))

        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return [addr for addr, _ in ranked[: self.max_per_hop]]

    @staticmethod
    def _get_balance(wallet_data: dict, chain: str):
        if chain == "bitcoin":
            return wallet_data.get("balance_btc", 0)
        if chain == "ethereum":
            return wallet_data.get("balance_eth", 0)
        if chain == "tron":
            return wallet_data.get("balance_trx", 0)
        return wallet_data.get("balance", 0)
