"""
modules/report.py — CryptoWalletOSINT
Generates analysis reports in JSON, TXT, and HTML formats.
All reports are saved in reports/<address[:8]>_<timestamp>/

Automatically screens the target + its counterparties (and any
multi-hop trace nodes) against the local sanctions/mixer watchlist.
"""

import json
import os
from datetime import datetime

from modules.screening import Screener
from modules.utils import extract_counterparties


class ReportGenerator:
    def __init__(self, address: str, chain: str,
                 wallet_data: dict, osint_data: dict = None,
                 trace_result: dict = None):
        self.address  = address
        self.chain    = chain
        self.wallet   = wallet_data
        self.osint    = osint_data or {}
        self.trace    = trace_result or {}
        self.ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir  = os.path.join("reports", f"{address[:8]}_{self.ts}")
        os.makedirs(self.out_dir, exist_ok=True)

        self.screener  = Screener()
        self.screening = self._run_screening()

    def _run_screening(self) -> dict:
        """Screen target + direct counterparties (and trace nodes, if any)."""
        addresses = {self.address}
        addresses |= extract_counterparties(self.address, self.wallet)
        if self.trace:
            addresses |= set(self.trace.get("nodes", {}).keys())
        return self.screener.check_many(addresses)

    # ── Entry point ───────────────────────────────────────────

    def generate(self, fmt: str = "all") -> list:
        """Generate reports. fmt: 'json' | 'txt' | 'html' | 'all'"""
        paths = []
        if fmt in ("json", "all"):
            paths.append(self._json())
        if fmt in ("txt", "all"):
            paths.append(self._txt())
        if fmt in ("html", "all"):
            paths.append(self._html())
        print(f"  [reports] Saved to → {self.out_dir}/")
        return paths

    # ── JSON ──────────────────────────────────────────────────

    def _json(self) -> str:
        payload = {
            "meta": {
                "tool":      "CryptoWalletOSINT",
                "version":   "1.1",
                "generated": datetime.now().isoformat(),
                "target":    self.address,
                "chain":     self.chain,
            },
            "blockchain":      self.wallet,
            "osint":           self.osint,
            "screening":       self.screening,
            "multihop_trace":  self.trace,
        }
        path = os.path.join(self.out_dir, "report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"  [+] JSON  → {path}")
        return path

    # ── TXT ───────────────────────────────────────────────────

    def _txt(self) -> str:
        W = self.wallet
        chain = W.get("chain", self.chain)
        lines = [
            "=" * 64,
            "          CryptoWallet OSINT Report",
            "=" * 64,
            f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Target    : {self.address}",
            f"Chain     : {chain.upper()}",
            "",
        ]

        # ── Wallet overview ──
        lines += ["── WALLET OVERVIEW " + "─" * 44]
        if chain == "bitcoin":
            lines += [
                f"  Balance        : {W.get('balance_btc', 0):.8f} BTC",
                f"  Total received : {W.get('total_received_btc', 0):.8f} BTC",
                f"  Total sent     : {W.get('total_sent_btc', 0):.8f} BTC",
            ]
        elif chain == "ethereum":
            lines.append(f"  Balance        : {W.get('balance_eth', 0):.6f} ETH")
        elif chain == "tron":
            lines.append(f"  Balance        : {W.get('balance_trx', 0):.2f} TRX")
        else:
            lines.append(f"  Balance        : {W.get('balance', 0)}")

        lines.append(f"  Transactions   : {W.get('tx_count', 0)}")
        label = W.get("label", "")
        if label:
            lines.append(f"  Entity/Label   : {label}")
        if "error" in W:
            lines.append(f"  ⚠ API Error    : {W['error']}")

        # ── Transactions ──
        lines += ["", "── TRANSACTIONS " + "─" * 47]
        txs = W.get("transactions", [])
        for i, tx in enumerate(txs[:30], 1):
            if chain == "bitcoin":
                lines.append(f"  [{i:02d}] TxID  : {tx.get('txid','?')}")
                lines.append(f"        Block : {tx.get('block','unconfirmed')}")
                for out in tx.get("outputs", [])[:3]:
                    lines.append(f"        → {out.get('address','?')}")
                    lines.append(f"          {out.get('value_btc',0):.8f} BTC")
                lines.append("")
            elif chain in ("ethereum", "tron"):
                key_val = "value_eth" if chain == "ethereum" else "value_trx"
                unit    = "ETH" if chain == "ethereum" else "TRX"
                frm = tx.get("from", "?")
                to  = tx.get("to",  "?")
                direction = "→ OUT" if (frm or "").lower() == self.address.lower() else "← IN"
                peer = to if "OUT" in direction else frm
                lines.append(f"  [{i:02d}] TxID        : {tx.get('txid','?')}")
                lines.append(f"        Direction   : {direction}")
                lines.append(f"        Counterpart : {peer}")
                lines.append(f"        Amount      : {tx.get(key_val,0):.6f} {unit}")
                lines.append("")

        # ── Screening (sanctions / mixer watchlist) ──
        lines += ["", "── SCREENING — SANCTIONS / MIXER WATCHLIST " + "─" * 21]
        if self.screening:
            lines.append(f"  🚨 {len(self.screening)} flagged address(es) found:")
            for addr, entry in self.screening.items():
                cats = ", ".join(entry.get("category", []))
                lines.append(f"    • {addr}")
                lines.append(f"      Entity   : {entry.get('entity','')}")
                lines.append(f"      Category : {cats}")
                lines.append(f"      Program  : {entry.get('program','')} ({entry.get('date','')})")
                lines.append(f"      Source   : {entry.get('source_url','')}")
                lines.append("")
        else:
            lines.append("  No flagged addresses found in the screened set.")
        meta = self.screener.stats()
        lines.append(
            f"  (Screened against a curated sample of {meta['total_entries']} "
            f"entries, last updated {meta['last_updated']} — not the full SDN list.)"
        )

        # ── Multi-hop trace summary ──
        if self.trace:
            lines += ["", "── MULTI-HOP TRACE " + "─" * 44]
            lines.append(f"  Depth          : {self.trace.get('depth', 1)} hop(s)")
            lines.append(f"  Total traced   : {self.trace.get('total_addresses', 0)} addresses")
            for hop, count in self.trace.get("hop_counts", {}).items():
                lines.append(f"  Hop {hop}          : {count} new address(es)")
            if self.trace.get("flagged"):
                lines.append(f"  ⚠ {len(self.trace['flagged'])} flagged address(es) within the traced graph")

        # ── OSINT ──
        if self.osint:
            lines += ["", "── OSINT FINDINGS " + "─" * 44]
            web    = self.osint.get("web", [])
            reddit = self.osint.get("reddit", [])
            github = self.osint.get("github", [])
            btalk  = self.osint.get("bitcointalk", [])
            ent    = self.osint.get("extracted_entities", {})

            lines.append(f"  Web results    : {len(web)}")
            for r in web[:4]:
                lines.append(f"    • {r.get('title','')[:55]}")
                lines.append(f"      {r.get('url','')[:70]}")

            lines.append(f"\n  Reddit results : {len(reddit)}")
            for r in reddit[:3]:
                lines.append(f"    • r/{r.get('subreddit','')} — {r.get('title','')[:50]}")
                lines.append(f"      Author: u/{r.get('author','')}  |  {r.get('url','')}")

            lines.append(f"\n  GitHub results : {len(github)}")
            for g in github[:3]:
                lines.append(f"    • {g.get('repo','')} / {g.get('file','')}")
                lines.append(f"      Owner: {g.get('repo_owner','')}  |  {g.get('url','')}")

            lines.append(f"\n  BitcoinTalk    : {len(btalk)}")
            for b in btalk[:3]:
                lines.append(f"    • {b.get('title','')[:55]}")

            if ent.get("emails"):
                lines.append(f"\n  Emails found   : {', '.join(ent['emails'][:5])}")
            if ent.get("phones"):
                lines.append(f"  Phones found   : {', '.join(ent['phones'][:3])}")
            if ent.get("usernames"):
                lines.append(f"  Usernames      : {', '.join(ent['usernames'][:6])}")
            if ent.get("telegrams"):
                lines.append(f"  Telegram       : {', '.join(ent['telegrams'][:4])}")

        lines += [
            "",
            "=" * 64,
            "  ⚠  For educational/research purposes only.",
            "=" * 64,
        ]

        path = os.path.join(self.out_dir, "report.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  [+] TXT   → {path}")
        return path

    # ── HTML ──────────────────────────────────────────────────

    def _html(self) -> str:
        W     = self.wallet
        chain = W.get("chain", self.chain)
        txs   = W.get("transactions", [])

        # Balance line
        if chain == "bitcoin":
            balance  = f"{W.get('balance_btc', 0):.8f} BTC"
            received = f"{W.get('total_received_btc', 0):.8f} BTC"
            sent     = f"{W.get('total_sent_btc', 0):.8f} BTC"
        elif chain == "ethereum":
            balance  = f"{W.get('balance_eth', 0):.6f} ETH"
            received = sent = "N/A"
        elif chain == "tron":
            balance  = f"{W.get('balance_trx', 0):.2f} TRX"
            received = sent = "N/A"
        else:
            balance  = str(W.get("balance", 0))
            received = sent = "N/A"

        # TX rows
        tx_rows = ""
        for tx in txs[:50]:
            if chain == "bitcoin":
                for out in tx.get("outputs", [])[:2]:
                    addr = out.get("address", "?")
                    val  = f"{out.get('value_btc', 0):.8f} BTC"
                    tx_rows += (
                        f"<tr><td class='m'>{tx.get('txid','?')}</td>"
                        f"<td><span class='out'>→ OUT</span></td>"
                        f"<td class='m'>{addr}</td>"
                        f"<td>{val}</td></tr>"
                    )
            elif chain in ("ethereum", "tron"):
                key_val = "value_eth" if chain == "ethereum" else "value_trx"
                unit    = "ETH" if chain == "ethereum" else "TRX"
                frm = tx.get("from", "")
                to  = tx.get("to",  "")
                is_out = (frm or "").lower() == self.address.lower()
                d_cls  = "out" if is_out else "in_"
                d_lbl  = "→ OUT" if is_out else "← IN"
                peer   = to if is_out else frm
                val    = f"{tx.get(key_val, 0):.6f} {unit}"
                tx_rows += (
                    f"<tr><td class='m'>{tx.get('txid','?')}</td>"
                    f"<td><span class='{d_cls}'>{d_lbl}</span></td>"
                    f"<td class='m'>{peer}</td>"
                    f"<td>{val}</td></tr>"
                )

        # Screening section
        screening_rows = "".join(
            f"<tr><td class='m'>{addr}</td><td>{entry.get('entity','')}</td>"
            f"<td>{', '.join(entry.get('category', []))}</td>"
            f"<td>{entry.get('program','')}<br><small>{entry.get('date','')}</small></td></tr>"
            for addr, entry in self.screening.items()
        )
        screening_meta = self.screener.stats()
        screening_html = f"""
<div class="card">
  <h2>🚨 Sanctions / Mixer Screening</h2>
  {'<div class="warn-strong">⚠ ' + str(len(self.screening)) + ' flagged address(es) found — see below.</div>'
    if self.screening else '<div class="ok">✓ No flagged addresses found in the screened set.</div>'}
  {f'''<table style="margin-top:14px">
    <tr><th>Address</th><th>Entity</th><th>Category</th><th>Program</th></tr>
    {screening_rows}
  </table>''' if self.screening else ''}
  <small style="display:block;margin-top:10px">
    Screened against a curated sample of {screening_meta['total_entries']} entries
    (last updated {screening_meta['last_updated']}) — not the full SDN list.
  </small>
</div>"""

        # Multi-hop trace section
        trace_html = ""
        if self.trace:
            hop_rows = "".join(
                f"<div class='stat'><span>{count}</span>Hop {hop}</div>"
                for hop, count in self.trace.get("hop_counts", {}).items()
            )
            trace_html = f"""
<div class="card">
  <h2>🔀 Multi-hop Trace</h2>
  <div class="grid4">
    <div class="stat"><span>{self.trace.get('depth',1)}</span>Depth</div>
    <div class="stat"><span>{self.trace.get('total_addresses',0)}</span>Total addresses</div>
    {hop_rows}
  </div>
</div>"""

        # OSINT section
        osint_html = ""
        if self.osint:
            web    = self.osint.get("web", [])
            reddit = self.osint.get("reddit", [])
            github = self.osint.get("github", [])
            btalk  = self.osint.get("bitcointalk", [])
            ent    = self.osint.get("extracted_entities", {})

            reddit_li = "".join(
                f"<li><a href='{r.get('url','')}' target='_blank'>"
                f"r/{r.get('subreddit','')} — {r.get('title','')[:60]}</a>"
                f" <span class='by'>u/{r.get('author','')}</span></li>"
                for r in reddit[:6]
            )
            github_li = "".join(
                f"<li><a href='{g.get('url','')}' target='_blank'>"
                f"{g.get('repo','')} / {g.get('file','')}</a></li>"
                for g in github[:6]
            )
            web_li = "".join(
                f"<li><a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:70]}</a></li>"
                for r in web[:6]
            )
            emails    = ", ".join(ent.get("emails", [])[:5])    or "—"
            phones    = ", ".join(ent.get("phones", [])[:3])    or "—"
            usernames = ", ".join(ent.get("usernames", [])[:6]) or "—"
            telegrams = ", ".join(ent.get("telegrams", [])[:4]) or "—"

            osint_html = f"""
<div class="card">
  <h2>🔍 OSINT Findings</h2>
  <div class="grid4">
    <div class="stat"><span>{len(web)}</span>Web results</div>
    <div class="stat"><span>{len(reddit)}</span>Reddit posts</div>
    <div class="stat"><span>{len(github)}</span>GitHub refs</div>
    <div class="stat"><span>{len(btalk)}</span>BitcoinTalk</div>
  </div>

  <h3>Extracted identifiers <small>(found in public posts near this address)</small></h3>
  <table>
    <tr><th>Type</th><th>Values</th></tr>
    <tr><td>📧 Emails</td><td>{emails}</td></tr>
    <tr><td>📞 Phones</td><td>{phones}</td></tr>
    <tr><td>👤 Usernames</td><td>{usernames}</td></tr>
    <tr><td>✈️ Telegram</td><td>{telegrams}</td></tr>
  </table>

  <h3>Web mentions</h3><ul>{web_li or '<li>No results</li>'}</ul>
  <h3>Reddit</h3><ul>{reddit_li or '<li>No results</li>'}</ul>
  <h3>GitHub</h3><ul>{github_li or '<li>No results</li>'}</ul>
</div>"""

        label_badge = (
            f"<span class='badge'>{W.get('label','')}</span>"
            if W.get("label") else ""
        )
        error_banner = (
            f"<div class='err'>⚠ API Error: {W['error']}</div>"
            if "error" in W else ""
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>OSINT — {self.address[:16]}…</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#0d0d1a;color:#e2e8f0;padding:20px}}
a{{color:#818cf8;text-decoration:none}}a:hover{{text-decoration:underline}}
.header{{background:linear-gradient(135deg,#1e1b4b,#312e81);padding:28px;border-radius:12px;margin-bottom:18px}}
.header h1{{color:#a5b4fc;font-size:22px;margin-bottom:8px}}
.addr{{font-family:monospace;font-size:13px;color:#c7d2fe;word-break:break-all}}
.chain-tag{{display:inline-block;background:#312e81;padding:2px 10px;border-radius:20px;font-size:11px;color:#a5b4fc;margin-top:8px}}
.badge{{background:#1e3a5f;color:#60a5fa;padding:2px 10px;border-radius:20px;font-size:11px;margin-left:8px}}
.card{{background:#13131f;border:1px solid #1e1b4b;border-radius:12px;padding:20px;margin-bottom:18px}}
h2{{color:#818cf8;font-size:17px;margin-bottom:14px}}
h3{{color:#a5b4fc;font-size:14px;margin:14px 0 8px}}
small{{color:#64748b;font-size:11px;margin-left:6px}}
.grid4{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:16px}}
.stat{{background:#0d0d1a;padding:14px;border-radius:8px;text-align:center;border:1px solid #1e1b4b}}
.stat span{{display:block;font-size:20px;color:#818cf8;font-weight:700;margin-bottom:4px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}}
th{{background:#0d0d1a;padding:9px 10px;text-align:left;color:#818cf8;font-weight:600}}
td{{padding:7px 10px;border-bottom:1px solid #1e1b4b}}
tr:hover td{{background:#1a1a30}}
.m{{font-family:monospace;word-break:break-all;font-size:11px}}
.out{{color:#f87171;font-weight:600}}
.in_{{color:#34d399;font-weight:600}}
.by{{color:#64748b;font-size:11px;margin-left:6px}}
ul{{list-style:none;padding:0}}
li{{padding:5px 0;border-bottom:1px solid #1e1b4b;font-size:12px}}
.err{{background:#1c0f0f;border:1px solid #7f1d1d;color:#fca5a5;padding:10px;border-radius:8px;margin-top:10px;font-size:12px}}
.warn{{background:#1a1200;border:1px solid #78350f;color:#fcd34d;padding:10px;border-radius:8px;text-align:center;font-size:12px;margin-top:20px}}
.warn-strong{{background:#1c0f0f;border:1px solid #7f1d1d;color:#fca5a5;padding:12px;border-radius:8px;font-weight:600;font-size:13px}}
.ok{{background:#0f1c14;border:1px solid #166534;color:#86efac;padding:12px;border-radius:8px;font-weight:600;font-size:13px}}
.ts{{font-size:11px;color:#475569;margin-top:6px}}
</style>
</head>
<body>
<div class="header">
  <h1>🔍 CryptoWallet OSINT Report</h1>
  <div class="addr">{self.address}</div>
  <div class="chain-tag">{chain.upper()}</div>{label_badge}
  <div class="ts">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
{error_banner}

<div class="card">
  <h2>💰 Wallet Overview</h2>
  <div class="grid4">
    <div class="stat"><span>{balance}</span>Balance</div>
    <div class="stat"><span>{received}</span>Received</div>
    <div class="stat"><span>{sent}</span>Sent</div>
    <div class="stat"><span>{W.get('tx_count',0)}</span>Transactions</div>
  </div>
</div>

<div class="card">
  <h2>📋 Transactions (last {min(len(txs),50)})</h2>
  <table>
    <tr><th>TxID</th><th>Direction</th><th>Counterpart</th><th>Amount</th></tr>
    {tx_rows or '<tr><td colspan="4">No transactions</td></tr>'}
  </table>
</div>

{osint_html}

{screening_html}

{trace_html}

<div class="warn">
  ⚠ This report was generated for educational / research purposes only.<br>
  All data comes from public blockchains and publicly accessible sources.
</div>
</body>
</html>"""

        path = os.path.join(self.out_dir, "report.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [+] HTML  → {path}")
        return path
