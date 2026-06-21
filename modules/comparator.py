"""
modules/comparator.py — CryptoWalletOSINT
Compares two or more wallets to find shared counterparties — direct
evidence that "different" wallets may be controlled by the same actor
(e.g. both send funds to the same exchange deposit address).
"""

import json
import os
from datetime import datetime
from itertools import combinations

from modules.utils import extract_counterparties


class WalletComparator:
    def __init__(self, wallets: dict):
        """wallets: {address: wallet_data} — already-fetched blockchain data."""
        self.wallets = wallets

    # ── Public API ───────────────────────────────────────────

    def compare(self) -> dict:
        """
        Returns:
          {
            "wallets": [addr, ...],
            "counterparties": {addr: [peer_addr, ...]},
            "shared": {shared_addr: [owners]},
            "pairwise_overlap": {"addrA <-> addrB": [shared_addrs]},
            "shared_count": n,
          }
        """
        peer_map = {addr: extract_counterparties(addr, wd) for addr, wd in self.wallets.items()}
        all_addrs = list(peer_map.keys())

        union_peers = set()
        for peers in peer_map.values():
            union_peers |= peers

        shared = {}
        for peer in union_peers:
            owners = [addr for addr in all_addrs if peer in peer_map[addr]]
            if len(owners) >= 2:
                shared[peer] = owners

        pairwise = {}
        for a, b in combinations(all_addrs, 2):
            common = peer_map[a] & peer_map[b]
            if common:
                pairwise[f"{a} <-> {b}"] = sorted(common)

        return {
            "wallets":          all_addrs,
            "counterparties":   {a: sorted(p) for a, p in peer_map.items()},
            "shared":           shared,
            "pairwise_overlap": pairwise,
            "shared_count":     len(shared),
        }

    # ── Report generation ─────────────────────────────────────

    def generate_report(self, result: dict, out_dir: str = "reports") -> dict:
        """Write JSON + TXT + HTML comparison reports. Returns their paths."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        comp_dir = os.path.join(out_dir, f"compare_{ts}")
        os.makedirs(comp_dir, exist_ok=True)

        json_path = self._write_json(result, comp_dir)
        txt_path  = self._write_txt(result, comp_dir)
        html_path = self._write_html(result, comp_dir)

        print(f"  [+] Comparison JSON → {json_path}")
        print(f"  [+] Comparison TXT  → {txt_path}")
        print(f"  [+] Comparison HTML → {html_path}")
        return {"json": json_path, "txt": txt_path, "html": html_path, "dir": comp_dir}

    def _write_json(self, result: dict, out_dir: str) -> str:
        path = os.path.join(out_dir, "comparison.json")
        payload = {
            "meta": {
                "tool":      "CryptoWalletOSINT",
                "generated": datetime.now().isoformat(),
                "type":      "wallet_comparison",
            },
            **result,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        return path

    def _write_txt(self, result: dict, out_dir: str) -> str:
        lines = [
            "=" * 64,
            "     CryptoWallet OSINT — Wallet Comparison Report",
            "=" * 64,
            f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Wallets   : {len(result['wallets'])}",
            "",
        ]
        for w in result["wallets"]:
            n_peers = len(result["counterparties"].get(w, []))
            lines.append(f"  • {w}  ({n_peers} counterparties)")

        lines += ["", "── SHARED COUNTERPARTIES " + "─" * 38]
        if result["shared"]:
            for addr, owners in result["shared"].items():
                lines.append(f"  {addr}")
                lines.append(f"    shared by: {', '.join(owners)}")
                lines.append("")
            lines.append(
                f"⚠ {result['shared_count']} address(es) are shared between 2+ "
                f"of the analyzed wallets — possible common ownership."
            )
        else:
            lines.append("  No shared counterparties found between the analyzed wallets.")

        lines += ["", "=" * 64, "  ⚠  For educational/research purposes only.", "=" * 64]

        path = os.path.join(out_dir, "comparison.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _write_html(self, result: dict, out_dir: str) -> str:
        wallet_rows = "".join(
            f"<tr><td class='m'>{w}</td><td>{len(result['counterparties'].get(w, []))}</td></tr>"
            for w in result["wallets"]
        )

        shared_rows = "".join(
            f"<tr><td class='m'>{addr}</td><td class='m'>{', '.join(owners)}</td></tr>"
            for addr, owners in result["shared"].items()
        ) or "<tr><td colspan='2'>No shared counterparties found.</td></tr>"

        verdict = (
            f"<div class='warn-strong'>⚠ {result['shared_count']} shared address(es) found — "
            f"possible common ownership between wallets.</div>"
            if result["shared_count"] else
            "<div class='ok'>✓ No shared counterparties — no evidence of common ownership found.</div>"
        )

        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Wallet Comparison</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#0d0d1a;color:#e2e8f0;padding:20px}}
.header{{background:linear-gradient(135deg,#1e1b4b,#312e81);padding:28px;border-radius:12px;margin-bottom:18px}}
.header h1{{color:#a5b4fc;font-size:22px}}
.card{{background:#13131f;border:1px solid #1e1b4b;border-radius:12px;padding:20px;margin-bottom:18px}}
h2{{color:#818cf8;font-size:17px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#0d0d1a;padding:9px 10px;text-align:left;color:#818cf8}}
td{{padding:7px 10px;border-bottom:1px solid #1e1b4b}}
.m{{font-family:monospace;word-break:break-all;font-size:11px}}
.warn-strong{{background:#1c0f0f;border:1px solid #7f1d1d;color:#fca5a5;padding:14px;border-radius:8px;font-weight:600}}
.ok{{background:#0f1c14;border:1px solid #166534;color:#86efac;padding:14px;border-radius:8px;font-weight:600}}
</style></head><body>
<div class="header"><h1>🔍 Wallet Comparison Report</h1>
<div style="font-size:11px;color:#94a3b8;margin-top:6px">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div></div>

<div class="card"><h2>Wallets analyzed</h2>
<table><tr><th>Address</th><th>Counterparties</th></tr>{wallet_rows}</table></div>

<div class="card"><h2>Shared counterparties</h2>
{verdict}
<table style="margin-top:14px"><tr><th>Shared address</th><th>Shared by</th></tr>{shared_rows}</table>
</div>

<div class="card" style="text-align:center;font-size:12px;color:#fcd34d;background:#1a1200;border-color:#78350f">
⚠ For educational / research purposes only.
</div>
</body></html>"""

        path = os.path.join(out_dir, "comparison.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
