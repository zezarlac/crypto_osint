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

    def visualize_hierarchical(self, output_name: str = "wallet", out_dir: str = ".") -> str:
        """Hierarchical layout: target center, hops in concentric rings."""
        if not self.G.nodes:
            return ""
        n = len(self.G.nodes)
        fig_w, fig_h = max(18, min(32, 12 + n * 0.7)), max(12, min(22, 8 + n * 0.5))
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#0d0d1a")

        pos, target, hops = {}, self.target, {}
        for nd in self.G.nodes():
            h = self.G.nodes[nd].get("hop", 1)
            if h not in hops: hops[h] = []
            hops[h].append(nd)
        pos[target] = (0, 0)
        for hop in sorted(hops.keys()):
            if hop == 0: continue
            for i, nd in enumerate(hops[hop]):
                radius, angle = 2.5 + (hop - 1) * 3.5, 2 * math.pi * i / max(len(hops[hop]), 1)
                pos[nd] = (radius * math.cos(angle), radius * math.sin(angle))

        nx.draw_networkx_edges(self.G, pos, edge_color="#94a3b8", arrows=True, arrowsize=16, alpha=0.45, width=1.0, ax=ax, connectionstyle="arc3,rad=0.08")
        nodelist = list(self.G.nodes())
        colors = [_HOP_COLORS.get(self.G.nodes[nd].get("hop", 1), "#6366f1") for nd in nodelist]
        sizes = [2400 if nd == target else 700 - (self.G.nodes[nd].get("hop", 1) - 1) * 100 for nd in nodelist]
        edge_colors = [_FLAG_BORDER if self.G.nodes[nd].get("flagged") else "#0d0d1a" for nd in nodelist]
        line_widths = [2.8 if self.G.nodes[nd].get("flagged") else 0.5 for nd in nodelist]

        nx.draw_networkx_nodes(self.G, pos, nodelist=nodelist, node_color=colors, node_size=sizes, alpha=0.95, ax=ax, edgecolors=edge_colors, linewidths=line_widths)

        labels = {nd: (_wrap_address(nd) + ("\n▶ TARGET" if nd == target else "") + (f"\n⚠ {self.G.nodes[nd]['flagged'].get('entity', 'FLAGGED')}" if self.G.nodes[nd].get("flagged") else "")) for nd in nodelist}
        nx.draw_networkx_labels(self.G, pos, labels, font_size=5.5, font_color="#e2e8f0", font_family="monospace", ax=ax, bbox=dict(facecolor="#13131f", edgecolor="#3730a3", boxstyle="round,pad=0.25", alpha=0.85, linewidth=0.6))

        legend_handles = [mpatches.Patch(color=_HOP_COLORS[0], label="Target"), mpatches.Patch(color=_HOP_COLORS[1], label="Hop 1")]
        if self.depth >= 2: legend_handles.append(mpatches.Patch(color=_HOP_COLORS[2], label="Hop 2"))
        if self.depth >= 3: legend_handles.append(mpatches.Patch(color=_HOP_COLORS[3], label="Hop 3"))
        if any(self.G.nodes[nd].get("flagged") for nd in nodelist): legend_handles.append(mpatches.Patch(facecolor="#1e1e3f", edgecolor=_FLAG_BORDER, linewidth=2.5, label="⚠ Flagged"))
        ax.legend(handles=legend_handles, facecolor="#1e1e3f", labelcolor="white", loc="upper left", fontsize=8)
        flagged_n = sum(1 for nd in nodelist if self.G.nodes[nd].get("flagged"))
        ax.set_title(f"Hierarchical Graph  |  {self.chain.upper()}  |  depth={self.depth}\n{self.target}\n{n} addresses · {len(self.G.edges)} connections" + (f"  ·  ⚠ {flagged_n} flagged" if flagged_n else ""), color="white", fontsize=9, pad=14, family="monospace")
        ax.axis("off")
        plt.tight_layout()
        os.makedirs(out_dir, exist_ok=True)
        fname = os.path.join(out_dir, f"graph_hierarchical_{self.target[:10]}.png")
        plt.savefig(fname, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        return fname

    def export_interactive_html(self, output_dir: str = ".") -> str:
        """Interactive D3.js graph: zoom, pan, filter by hop, click for details."""
        data = nx.node_link_data(self.G)
        for node in data["nodes"]:
            attrs = self.G.nodes[node["id"]]
            node["hop"], node["flagged"] = attrs.get("hop", 1), bool(attrs.get("flagged"))
            if attrs.get("flagged"): node["entity"] = attrs["flagged"].get("entity", "")

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"><title>Interactive Graph</title>
<script src="https://d3js.org/d3.v7.min.js"></script><style>
body{{background:#0d0d1a;color:#e2e8f0;margin:0;padding:10px;font-family:Segoe UI}}
#container{{width:100%;height:100vh}}
svg{{background:#0d0d1a;border:1px solid #1e1b4b;border-radius:8px}}
#info,#controls{{position:absolute;background:#13131f;border:1px solid #1e1b4b;padding:12px;border-radius:8px;font-size:12px;z-index:10}}
#info{{top:10px;left:10px;max-width:360px}}
#controls{{bottom:10px;left:10px}}
button{{background:#312e81;color:#a5b4fc;border:1px solid #3730a3;padding:6px 12px;border-radius:4px;cursor:pointer;margin:2px;font-size:11px}}
button:hover{{background:#3730a3}}
.node{{cursor:pointer}}
.node.flagged{{stroke:#facc15!important;stroke-width:2.5px}}
.link{{stroke:#94a3b8;stroke-opacity:0.5}}
text{{pointer-events:none;font-size:9px;fill:#e2e8f0}}
#addr-full{{font-family:monospace;font-size:10px;word-break:break-all;color:#a5b4fc;margin-top:4px;line-height:1.5}}
.flag-badge{{color:#facc15;font-weight:600;margin-top:4px}}
.hop-badge{{display:inline-block;padding:1px 7px;border-radius:8px;font-size:10px;margin-top:4px}}
</style></head><body>
<div id="container"><svg id="graph"></svg></div>
<div id="info">
  <strong style="color:#818cf8">🔍 Click a node to inspect</strong>
  <div id="selected-info" style="margin-top:8px"></div>
</div>
<div id="controls">
  Filter:
  <select id="hop-filter" style="background:#312e81;color:#a5b4fc;border:1px solid #3730a3;padding:4px">
    <option value="">All hops</option>
    <option value="1">≤ 1 hop</option>
    <option value="2">≤ 2 hops</option>
    <option value="3">≤ 3 hops</option>
  </select>
  <button onclick="resetZoom()">Reset Zoom</button>
</div>

<script>
const data={json.dumps(data)};
const width=window.innerWidth-20, height=window.innerHeight-20;
const svg=d3.select("#graph").attr("width",width).attr("height",height);
const g=svg.append("g");
svg.call(d3.zoom().on("zoom",e=>g.attr("transform",e.transform)));

const hopColor=d3.scaleOrdinal().domain([0,1,2,3]).range(["#ef4444","#6366f1","#22d3ee","#f59e0b"]);
const hopLabel={{0:"Target",1:"Hop 1",2:"Hop 2",3:"Hop 3"}};

const sim=d3.forceSimulation(data.nodes)
  .force("link",d3.forceLink(data.links).id(d=>d.id).distance(70))
  .force("charge",d3.forceManyBody().strength(-320))
  .force("center",d3.forceCenter(width/2,height/2))
  .force("collision",d3.forceCollide().radius(18));

const link=g.selectAll(".link").data(data.links).enter()
  .append("line").attr("class","link").attr("stroke","#94a3b8").attr("stroke-width",1.5);

const node=g.selectAll(".node").data(data.nodes).enter()
  .append("circle")
  .attr("class",d=>"node"+(d.flagged?" flagged":""))
  .attr("r",d=>d.id==="{self.target}"?14:7)
  .attr("fill",d=>hopColor(d.hop))
  .attr("stroke",d=>d.flagged?"#facc15":"#0d0d1a")
  .attr("stroke-width",d=>d.flagged?2.5:1.5)
  .on("click",(e,d)=>{{
    const hopBg={{0:"#450a0a",1:"#1e1b4b",2:"#0c2e33",3:"#1c1000"}};
    const flagHtml=d.flagged
      ? `<div class="flag-badge">⚠ ${{d.entity}}</div>` : "";
    document.getElementById("selected-info").innerHTML=`
      <div class="hop-badge" style="background:${{hopBg[d.hop]||"#1e1b4b"}};color:${{hopColor(d.hop)}}">
        ${{hopLabel[d.hop]||"Hop "+d.hop}}
      </div>
      ${{flagHtml}}
      <div id="addr-full">${{d.id}}</div>
      <button onclick="navigator.clipboard.writeText('${{d.id}}').then(()=>this.textContent='✓ Copied').catch(()=>{{}})"
        style="margin-top:6px;font-size:10px;padding:3px 8px">Copy address</button>
    `;
  }})
  .call(d3.drag()
    .on("start",e=>{{if(!e.active)sim.alphaTarget(0.3).restart();e.subject.fx=e.x;e.subject.fy=e.y;}})
    .on("drag",e=>{{e.subject.fx=e.x;e.subject.fy=e.y;}})
    .on("end",e=>{{if(!e.active)sim.alphaTarget(0);e.subject.fx=null;e.subject.fy=null;}}));

const labels=g.selectAll(".label").data(data.nodes).enter()
  .append("text")
  .attr("text-anchor","middle")
  .attr("dy",".3em")
  .text(d=>d.id.substring(0,6)+"…"+d.id.slice(-4))
  .style("font-size","8px")
  .style("font-family","monospace");

sim.on("tick",()=>{{
  link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
      .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  node.attr("cx",d=>d.x).attr("cy",d=>d.y);
  labels.attr("x",d=>d.x).attr("y",d=>d.y);
}});

document.getElementById("hop-filter").addEventListener("change",e=>{{
  const f=e.target.value?parseInt(e.target.value):null;
  node.style("opacity",d=>!f||d.hop<=f?1:0.1);
  link.style("opacity",d=>!f||(d.source.hop<=f&&d.target.hop<=f)?0.5:0.05);
}});

function resetZoom(){{
  svg.transition().duration(750).call(
    d3.zoom().transform, d3.zoomIdentity.translate(width/2,height/2).scale(1)
  );
}}
</script></body></html>"""
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"graph_interactive_{self.target[:10]}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def export_sankey_html(self, output_dir: str = ".") -> str:
        """Sankey diagram showing money flow between wallets."""
        nodes_list, node_idx = list(self.G.nodes()), {}
        for i, n in enumerate(nodes_list): node_idx[n] = i
        sankey_nodes = [{"name": (n[:10]+"…") if n != self.target else "TARGET",
                         "fullAddr": n,
                         "hop": self.G.nodes[n].get("hop", 1),
                         "flagged": bool(self.G.nodes[n].get("flagged")),
                         "entity": self.G.nodes[n].get("flagged", {}).get("entity", "") if self.G.nodes[n].get("flagged") else ""}
                        for n in nodes_list]
        sankey_links = [{"source": node_idx[src], "target": node_idx[dst], "value": max(0.1, data.get("value", 0.001))} for src, dst, data in self.G.edges(data=True)]

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Money Flow (Sankey)</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
<style>
body{{background:#0d0d1a;color:#e2e8f0;margin:0;padding:20px;font-family:Segoe UI}}
h2{{color:#a5b4fc;margin-bottom:4px}}
.subtitle{{font-size:11px;color:#64748b;font-family:monospace;word-break:break-all;margin-bottom:16px}}
svg{{background:#0d0d1a}}
.node rect{{stroke-width:1px;rx:3}}
.link{{stroke-opacity:0.45;fill:none}}
.link:hover{{stroke-opacity:0.75}}
.flagged rect{{stroke:#facc15!important;stroke-width:2px}}
.node-label{{font-size:11px;fill:#e2e8f0;font-family:monospace}}
#tooltip{{position:fixed;background:#13131f;border:1px solid #1e1b4b;padding:8px 12px;
          border-radius:6px;font-size:11px;pointer-events:none;display:none;max-width:350px;
          word-break:break-all;font-family:monospace}}
</style></head><body>
<h2>💰 Money Flow Diagram</h2>
<div class="subtitle">{self.target}</div>
<div id="tooltip"></div>
<svg id="sankey"></svg>

<script>
const nodes = {json.dumps(sankey_nodes)};
const links = {json.dumps(sankey_links)};

const margin = {{top: 10, right: 160, bottom: 10, left: 10}};
const width  = Math.min(1300, window.innerWidth - 40) - margin.left - margin.right;
const height = Math.max(500, nodes.length * 32);

const svg = d3.select("#sankey")
  .attr("width",  width + margin.left + margin.right)
  .attr("height", height + margin.top  + margin.bottom)
  .append("g")
  .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const hopColor = d3.scaleOrdinal()
  .domain([0, 1, 2, 3])
  .range(["#ef4444", "#6366f1", "#22d3ee", "#f59e0b"]);

// Build Sankey layout using the d3-sankey plugin (d3Sankey global)
const sankeyLayout = d3Sankey.sankey()
  .nodeId(d => d.id)
  .nodeWidth(18)
  .nodePadding(Math.max(20, Math.min(60, height / nodes.length / 1.5)))
  .extent([[0, 0], [width, height]]);

// Give each node a stable id matching the index
const graphNodes = nodes.map((d, i) => Object.assign({{}}, d, {{id: i}}));
const graphLinks = links.map(l => Object.assign({{}}, l));

const {{nodes: sn, links: sl}} = sankeyLayout({{nodes: graphNodes, links: graphLinks}});

// ── Links ──────────────────────────────────────────
const linkSel = svg.selectAll(".link")
  .data(sl).enter().append("path")
  .attr("class", "link")
  .attr("d", d3Sankey.sankeyLinkHorizontal())
  .attr("stroke", d => hopColor(Math.max(d.source.hop || 0, d.target.hop || 0)))
  .attr("stroke-width", d => Math.max(1.5, d.width));

const tip = document.getElementById("tooltip");

linkSel
  .on("mousemove", (e, d) => {{
    tip.style.display = "block";
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top  = (e.clientY - 10) + "px";
    tip.innerHTML  = `<strong>Transfer</strong><br>
      From: ${{d.source.name}}<br>
      To: ${{d.target.name}}<br>
      Value: ${{d.value.toFixed(6)}}`;
  }})
  .on("mouseleave", () => tip.style.display = "none");

// ── Nodes ──────────────────────────────────────────
const nodeGroup = svg.selectAll(".node")
  .data(sn).enter().append("g")
  .attr("class", d => "node" + (d.flagged ? " flagged" : ""));

nodeGroup.append("rect")
  .attr("x",      d => d.x0)
  .attr("y",      d => d.y0)
  .attr("height", d => Math.max(2, d.y1 - d.y0))
  .attr("width",  d => d.x1 - d.x0)
  .attr("fill",   d => hopColor(d.hop || 0))
  .attr("stroke", d => d.flagged ? "#facc15" : "#0d0d1a")
  .on("mousemove", (e, d) => {{
    tip.style.display = "block";
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top  = (e.clientY - 10) + "px";
    tip.innerHTML  = `<strong>${{d.flagged ? "⚠ " + d.entity : "Wallet"}}</strong><br>${{d.fullAddr || d.name}}`;
  }})
  .on("mouseleave", () => tip.style.display = "none");

// ── Labels (full address, right-aligned, monospace) ──
nodeGroup.append("text")
  .attr("class", "node-label")
  .attr("x", d => d.x1 + 6)
  .attr("y", d => (d.y0 + d.y1) / 2)
  .attr("dy", "0.35em")
  .attr("text-anchor", "start")
  .text(d => d.fullAddr || d.name)
  .append("title")               // native tooltip as fallback
  .text(d => d.fullAddr || d.name);

// Legend
const legendData = [
  {{hop:0, label:"Target"}},
  {{hop:1, label:"Hop 1"}},
  {{hop:2, label:"Hop 2"}},
  {{hop:3, label:"Hop 3"}},
];
const legend = svg.append("g").attr("transform", `translate(0, ${{height + 30}})`);
legendData.forEach((d, i) => {{
  const lg = legend.append("g").attr("transform", `translate(${{i * 110}}, 0)`);
  lg.append("rect").attr("width", 12).attr("height", 12).attr("fill", hopColor(d.hop)).attr("rx", 2);
  lg.append("text").attr("x", 16).attr("y", 10).attr("fill", "#e2e8f0").style("font-size", "11px").text(d.label);
}});
</script>
</body></html>"""

        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"graph_sankey_{self.target[:10]}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

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
