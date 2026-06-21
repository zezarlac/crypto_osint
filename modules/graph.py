"""
modules/graph.py — CryptoWalletOSINT
Builds and visualizes a directed transaction graph from wallet data
using NetworkX + Matplotlib.

Supports two build modes:
  • build()        — single-hop graph from one wallet's transactions
  • from_trace()    — multi-hop graph from a MultiHopTracer result

Every node is automatically screened against the local sanctions/
mixer watchlist (modules/screening.py) and flagged addresses are
highlighted with a yellow ring + warning label.
"""

import json
import os
import math
import networkx as nx
import matplotlib
matplotlib.use("Agg")  # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from modules.utils import extract_edges
from modules.screening import Screener

# Node color by hop distance from the target (0 = target itself)
_HOP_COLORS = {
    0: "#ef4444",   # target — red
    1: "#6366f1",   # hop 1  — indigo
    2: "#22d3ee",   # hop 2  — cyan
    3: "#f59e0b",   # hop 3  — amber
}
_FLAG_BORDER = "#facc15"   # yellow ring for sanctions/mixer matches


def _wrap_address(addr: str, width: int = 21) -> str:
    """
    Break a long address into multiple lines for readability
    WITHOUT cutting any characters — the full address is preserved.
    """
    if not addr or len(addr) <= width:
        return addr
    return "\n".join(addr[i:i + width] for i in range(0, len(addr), width))


class TransactionGraph:
    def __init__(self, wallet_data: dict, depth: int = 1):
        self.data     = wallet_data
        self.depth    = depth
        self.G        = nx.DiGraph()
        self.target   = wallet_data.get("address", "")
        self.chain    = wallet_data.get("chain", "")
        self.screener = Screener()

    # ── Build: single-hop (from one wallet's tx data) ───────────

    def build(self):
        """Populate the graph from the target wallet's own transactions (1 hop)."""
        self.G.add_node(self.target, kind="target", hop=0)
        self._screen_and_tag(self.target)

        edges = extract_edges(self.target, self.data, hop=1)
        for e in edges:
            for node in (e["from"], e["to"]):
                if node not in self.G:
                    self.G.add_node(node, kind="related", hop=1)
                    self._screen_and_tag(node)
            self.G.add_edge(e["from"], e["to"], txid=e["txid"], value=e.get("value", 0), hop=1)

    # ── Build: multi-hop (from a MultiHopTracer result) ─────────

    @classmethod
    def from_trace(cls, trace_result: dict) -> "TransactionGraph":
        """Build a graph directly from MultiHopTracer.trace() output."""
        g = cls.__new__(cls)
        g.data     = {}
        g.target   = trace_result.get("target", "")
        g.chain    = trace_result.get("chain", "")
        g.depth    = trace_result.get("depth", 1)
        g.G        = nx.DiGraph()
        g.screener = Screener()

        for addr, meta in trace_result.get("nodes", {}).items():
            hop  = meta.get("hop", 1)
            kind = "target" if hop == 0 else "related"
            g.G.add_node(addr, kind=kind, hop=hop)
            if meta.get("flagged"):
                g.G.nodes[addr]["flagged"] = meta["flagged"]

        for e in trace_result.get("edges", []):
            frm, to = e["from"], e["to"]
            for node in (frm, to):
                if node not in g.G:
                    g.G.add_node(node, kind="related", hop=e.get("hop", 1))
            g.G.add_edge(frm, to, txid=e.get("txid", "?"),
                         value=e.get("value", 0), hop=e.get("hop", 1))
        return g

    def _screen_and_tag(self, address: str):
        match = self.screener.check(address)
        if match:
            self.G.nodes[address]["flagged"] = match

    # ── Visualize ─────────────────────────────────────────────

    def visualize(self, output_name: str = "wallet", out_dir: str = ".") -> str:
        """
        Render the graph to a PNG file and return its path.
        Full wallet addresses are shown (wrapped, never truncated).
        Sanctioned/mixer addresses get a yellow ring + ⚠ label.
        """
        if not self.G.nodes:
            print("  [graph] No nodes to render.")
            return ""

        n = len(self.G.nodes)
        fig_w = max(20, min(34, 14 + n * 0.9))
        fig_h = max(14, min(24, 10 + n * 0.6))
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#0d0d1a")

        if n <= 25:
            pos = nx.spring_layout(self.G, k=3.6 / math.sqrt(max(n, 1)) * 2.2,
                                    seed=42, iterations=120)
        else:
            pos = nx.shell_layout(self.G)

        nodelist = list(self.G.nodes())
        colors, sizes, edge_colors, line_widths = [], [], [], []
        for node in nodelist:
            attrs = self.G.nodes[node]
            hop = attrs.get("hop", 1)
            colors.append(_HOP_COLORS.get(hop, "#6366f1"))
            sizes.append(2600 if hop == 0 else 900)
            if attrs.get("flagged"):
                edge_colors.append(_FLAG_BORDER)
                line_widths.append(3.2)
            else:
                edge_colors.append("#0d0d1a")
                line_widths.append(0.5)

        nx.draw_networkx_nodes(
            self.G, pos, nodelist=nodelist, node_color=colors, node_size=sizes,
            alpha=0.95, ax=ax, edgecolors=edge_colors, linewidths=line_widths,
        )
        nx.draw_networkx_edges(
            self.G, pos,
            edge_color="#94a3b8", arrows=True, arrowsize=18,
            alpha=0.55, width=1.2, ax=ax,
            connectionstyle="arc3,rad=0.08",
        )

        # ── Full-address labels (wrapped, never truncated) ──
        labels = {}
        for nd in nodelist:
            attrs = self.G.nodes[nd]
            wrapped = _wrap_address(nd)
            if attrs.get("hop") == 0:
                wrapped += "\n▶ TARGET"
            if attrs.get("flagged"):
                entity = attrs["flagged"].get("entity", "FLAGGED")
                wrapped += f"\n⚠ {entity}"
            labels[nd] = wrapped

        nx.draw_networkx_labels(
            self.G, pos, labels,
            font_size=6.5, font_color="#e2e8f0", font_family="monospace", ax=ax,
            bbox=dict(facecolor="#13131f", edgecolor="#3730a3",
                      boxstyle="round,pad=0.3", alpha=0.88, linewidth=0.8),
        )

        # ── Legend ──
        legend_handles = [
            mpatches.Patch(color=_HOP_COLORS[0], label="Target wallet"),
            mpatches.Patch(color=_HOP_COLORS[1], label="1 hop"),
        ]
        if self.depth >= 2:
            legend_handles.append(mpatches.Patch(color=_HOP_COLORS[2], label="2 hops"))
        if self.depth >= 3:
            legend_handles.append(mpatches.Patch(color=_HOP_COLORS[3], label="3 hops"))
        if any(self.G.nodes[nd].get("flagged") for nd in nodelist):
            legend_handles.append(mpatches.Patch(
                facecolor="#1e1e3f", edgecolor=_FLAG_BORDER, linewidth=2.5,
                label="⚠ Sanctions/Mixer match"
            ))

        ax.legend(
            handles=legend_handles,
            facecolor="#1e1e3f", labelcolor="white",
            loc="upper left", fontsize=9,
        )

        flagged_n = sum(1 for nd in nodelist if self.G.nodes[nd].get("flagged"))
        warn_txt = f"  ·  ⚠ {flagged_n} flagged address(es)" if flagged_n else ""
        ax.set_title(
            f"Transaction Graph  |  {self.chain.upper()}  |  depth={self.depth}\n"
            f"{self.target}\n"
            f"{n} addresses · {len(self.G.edges)} connections{warn_txt}",
            color="white", fontsize=10, pad=16, family="monospace",
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
        """Return basic graph statistics, including any flagged addresses."""
        top5 = sorted(self.G.degree(), key=lambda x: x[1], reverse=True)[:5]
        flagged = {nd: self.G.nodes[nd]["flagged"]
                   for nd in self.G.nodes if self.G.nodes[nd].get("flagged")}
        return {
            "nodes":            len(self.G.nodes),
            "edges":            len(self.G.edges),
            "unique_addresses": list(self.G.nodes),
            "most_connected":   top5,
            "flagged":          flagged,
        }

    def export_json(self, path: str = "graph.json") -> str:
        """Export graph as node-link JSON (compatible with D3.js etc.)."""
        data = nx.node_link_data(self.G)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return path
