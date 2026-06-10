"""
modules/graph.py — CryptoWalletOSINT
Builds and visualizes a directed transaction graph
from wallet data using NetworkX + Matplotlib.

Nodes = wallet addresses
Edges = transactions (directed: sender → receiver)
"""

import json
import os
import networkx as nx
import matplotlib
matplotlib.use("Agg")  # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


class TransactionGraph:
    def __init__(self, wallet_data: dict, depth: int = 2):
        self.data    = wallet_data
        self.depth   = depth
        self.G       = nx.DiGraph()
        self.target  = wallet_data.get("address", "")
        self.chain   = wallet_data.get("chain", "")

    # ── Build ──────────────────────────────────────────────────

    def build(self):
        """Populate the graph from transaction data."""
        self.G.add_node(self.target, kind="target")

        builders = {
            "bitcoin":  self._build_bitcoin,
            "ethereum": self._build_ethereum,
            "tron":     self._build_generic_from_to,
        }
        builder = builders.get(self.chain, self._build_generic_from_to)
        builder(self.data.get("transactions", []))

    def _build_bitcoin(self, txs: list):
        for tx in txs:
            txid_short = (tx.get("txid") or "?")[:8] + "…"

            # inputs → target  (money arrived)
            for inp in tx.get("inputs", []):
                if inp and inp not in ("unknown", "coinbase", self.target):
                    self._add_node(inp)
                    self.G.add_edge(inp, self.target, label=txid_short)

            # target → outputs  (money left)
            for out in tx.get("outputs", []):
                addr = out.get("address", "")
                if addr and addr not in ("unknown", self.target):
                    self._add_node(addr)
                    self.G.add_edge(
                        self.target, addr,
                        label=txid_short,
                        value=out.get("value_btc", 0),
                    )

    def _build_ethereum(self, txs: list):
        for tx in txs:
            txid_short = (tx.get("txid") or "?")[:8] + "…"
            frm = (tx.get("from") or "").lower()
            to  = (tx.get("to")   or "").lower()
            tgt = self.target.lower()
            val = tx.get("value_eth", 0)

            if frm and frm != tgt:
                self._add_node(frm)
                self.G.add_edge(frm, self.target, label=txid_short, value=val)

            if to and to != tgt:
                self._add_node(to)
                self.G.add_edge(self.target, to, label=txid_short, value=val)

    def _build_generic_from_to(self, txs: list):
        """Fallback for TRX and other from/to chains."""
        for tx in txs:
            txid_short = (tx.get("txid") or "?")[:8] + "…"
            frm = tx.get("from", "")
            to  = tx.get("to",   "")

            if frm and frm != self.target:
                self._add_node(frm)
                self.G.add_edge(frm, self.target, label=txid_short)
            if to and to != self.target:
                self._add_node(to)
                self.G.add_edge(self.target, to, label=txid_short)

    def _add_node(self, address: str):
        if address not in self.G:
            self.G.add_node(address, kind="related")

    # ── Visualize ─────────────────────────────────────────────

    def visualize(self, output_name: str = "wallet", out_dir: str = ".") -> str:
        """
        Render the graph to a PNG file and return its path.
        Uses a dark background with the target node highlighted.
        """
        if not self.G.nodes:
            print("  [graph] No nodes to render.")
            return ""

        n = len(self.G.nodes)
        fig, ax = plt.subplots(figsize=(16, 11))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#0d0d1a")

        # Layout: spring for small graphs, shell for large ones
        if n <= 25:
            pos = nx.spring_layout(self.G, k=2.5, seed=42, iterations=80)
        else:
            pos = nx.shell_layout(self.G)

        # Color & size per node type
        colors, sizes = [], []
        for node in self.G.nodes():
            if node == self.target or node == self.target.lower():
                colors.append("#ef4444")   # red — target
                sizes.append(2400)
            else:
                colors.append("#6366f1")   # indigo — related
                sizes.append(700)

        nx.draw_networkx_nodes(
            self.G, pos, node_color=colors, node_size=sizes, alpha=0.92, ax=ax
        )
        nx.draw_networkx_edges(
            self.G, pos,
            edge_color="#94a3b8", arrows=True, arrowsize=18,
            alpha=0.55, width=1.2, ax=ax,
            connectionstyle="arc3,rad=0.08",
        )

        # Shortened address labels
        labels = {
            nd: (nd[:6] + "…" + nd[-4:] + ("\n▶ TARGET" if nd in (self.target, self.target.lower()) else ""))
            for nd in self.G.nodes()
        }
        nx.draw_networkx_labels(
            self.G, pos, labels,
            font_size=6.5, font_color="#e2e8f0", ax=ax,
        )

        # Legend
        ax.legend(
            handles=[
                mpatches.Patch(color="#ef4444", label="Target wallet"),
                mpatches.Patch(color="#6366f1", label="Related wallets"),
            ],
            facecolor="#1e1e3f", labelcolor="white",
            loc="upper left", fontsize=9,
        )

        short = self.target[:12] + "…" + self.target[-6:]
        ax.set_title(
            f"Transaction Graph  |  {self.chain.upper()}  |  {short}\n"
            f"{n} addresses · {len(self.G.edges)} connections",
            color="white", fontsize=11, pad=14,
        )
        ax.axis("off")
        plt.tight_layout()

        os.makedirs(out_dir, exist_ok=True)
        fname = os.path.join(out_dir, f"graph_{self.target[:10]}.png")
        plt.savefig(fname, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        return fname

    # ── Stats & Export ────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return basic graph statistics."""
        top5 = sorted(self.G.degree(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "nodes":           len(self.G.nodes),
            "edges":           len(self.G.edges),
            "unique_addresses": list(self.G.nodes),
            "most_connected":  top5,
        }

    def export_json(self, path: str = "graph.json") -> str:
        """Export graph as node-link JSON (compatible with D3.js etc.)."""
        data = nx.node_link_data(self.G)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
