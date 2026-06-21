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
            web      = self.osint.get("web", [])
            reddit   = self.osint.get("reddit", [])
            github   = self.osint.get("github", [])
            btalk    = self.osint.get("bitcointalk", [])
            twitter  = self.osint.get("twitter", [])
            telegram = self.osint.get("telegram", [])
            reddit_c = self.osint.get("reddit_comments", [])
            dorks    = self.osint.get("dorks", [])
            onchain  = self.osint.get("onchain_comments", [])
            pivot    = self.osint.get("pivot", {})
            ent      = self.osint.get("extracted_entities", {})

            def _filtered(bucket):
                """Only show high/medium confidence hits; count the rest."""
                shown  = [r for r in bucket if r.get("confidence") in ("high", "medium")]
                hidden = len(bucket) - len(shown)
                return shown, hidden

            web_s, web_h = _filtered(web)
            lines.append(f"  Web results    : {len(web)}  ({web_h} low-confidence omitted)" if web_h else f"  Web results    : {len(web)}")
            for r in web_s[:4]:
                lines.append(f"    • [{r.get('confidence','?')}] {r.get('title','')[:50]}")
                lines.append(f"      {r.get('url','')[:70]}")

            lines.append(f"\n  Reddit posts   : {len(reddit)}")
            for r in reddit[:3]:
                lines.append(f"    • r/{r.get('subreddit','')} — {r.get('title','')[:50]}")
                lines.append(f"      Author: u/{r.get('author','')}  |  {r.get('url','')}")

            rc_s, rc_h = _filtered(reddit_c)
            lines.append(f"  Reddit comments: {len(reddit_c)}  ({rc_h} low-confidence omitted)" if rc_h else f"  Reddit comments: {len(reddit_c)}")
            for r in rc_s[:3]:
                lines.append(f"    • [{r.get('confidence','?')}] {r.get('title','')[:55]}")

            tw_s, tw_h = _filtered(twitter)
            lines.append(f"\n  Twitter/X      : {len(twitter)}  ({tw_h} low-confidence omitted)" if tw_h else f"\n  Twitter/X      : {len(twitter)}")
            for r in tw_s[:3]:
                lines.append(f"    • [{r.get('confidence','?')}] {r.get('title','')[:55]}")

            tg_s, tg_h = _filtered(telegram)
            lines.append(f"  Telegram       : {len(telegram)}  ({tg_h} low-confidence omitted)" if tg_h else f"  Telegram       : {len(telegram)}")
            for r in tg_s[:3]:
                lines.append(f"    • [{r.get('confidence','?')}] {r.get('title','')[:55]}")

            lines.append(f"\n  GitHub results : {len(github)}")
            for g in github[:3]:
                lines.append(f"    • {g.get('repo','')} / {g.get('file','')}")
                lines.append(f"      Owner: {g.get('repo_owner','')}  |  {g.get('url','')}")

            lines.append(f"\n  BitcoinTalk    : {len(btalk)}")
            for b in btalk[:3]:
                lines.append(f"    • {b.get('title','')[:55]}")

            dk_s, dk_h = _filtered(dorks)
            lines.append(f"\n  Dorks (leaks)  : {len(dorks)}  ({dk_h} low-confidence omitted)" if dk_h else f"\n  Dorks (leaks)  : {len(dorks)}")
            for r in dk_s[:5]:
                lines.append(f"    • [{r.get('dork','?')}] [{r.get('confidence','?')}] {r.get('title','')[:45]}")
                lines.append(f"      {r.get('url','')[:70]}")

            lines.append(f"\n  On-chain tags  : {len(onchain)}")
            for o in onchain[:5]:
                if "error" not in o:
                    lines.append(f"    • [{o.get('source','')}] {o.get('text','')[:70]}")

            if ent.get("emails"):
                lines.append(f"\n  Emails found   : {', '.join(ent['emails'][:5])}")
            if ent.get("phones"):
                lines.append(f"  Phones found   : {', '.join(ent['phones'][:3])}")
            if ent.get("usernames"):
                lines.append(f"  Usernames      : {', '.join(ent['usernames'][:6])}")
            if ent.get("telegrams"):
                lines.append(f"  Telegram       : {', '.join(ent['telegrams'][:4])}")

            # ── Identity pivot ──
            if pivot.get("usernames") or pivot.get("emails"):
                lines += ["", "── IDENTITY PIVOT (cross-platform check) " + "─" * 23]
                for username, checks in pivot.get("usernames", {}).items():
                    gh, kb, tg = checks.get("github", {}), checks.get("keybase", {}), checks.get("telegram", {})
                    lines.append(f"  @{username}")
                    if gh.get("exists"):
                        lines.append(f"    ✓ GitHub   : {gh.get('url','')} ({gh.get('public_repos',0)} repos)")
                    if kb.get("exists"):
                        lines.append(f"    ✓ Keybase  : linked to {', '.join(kb.get('linked_proofs', [])) or '—'}")
                    if tg.get("exists"):
                        lines.append(f"    ✓ Telegram : {tg.get('url','')}")
                    if not any((gh.get("exists"), kb.get("exists"), tg.get("exists"))):
                        lines.append("    (no matches on checked platforms)")
                for email, checks in pivot.get("emails", {}).items():
                    gr, gc = checks.get("gravatar", {}), checks.get("github_commits", {})
                    lines.append(f"  {email}")
                    if gr.get("exists"):
                        lines.append(f"    ✓ Gravatar : {gr.get('display_name','')} — {gr.get('profile_url','')}")
                    if gc.get("exists"):
                        lines.append(f"    ✓ GitHub commits : {gc.get('github_username','')} ({gc.get('commits_found',0)} commit(s))")
                    if not any((gr.get("exists"), gc.get("exists"))):
                        lines.append("    (no matches on checked platforms)")

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
        pivot_html = ""
        if self.osint:
            web      = self.osint.get("web", [])
            reddit   = self.osint.get("reddit", [])
            github   = self.osint.get("github", [])
            btalk    = self.osint.get("bitcointalk", [])
            twitter  = self.osint.get("twitter", [])
            telegram = self.osint.get("telegram", [])
            reddit_c = self.osint.get("reddit_comments", [])
            dorks    = self.osint.get("dorks", [])
            onchain  = self.osint.get("onchain_comments", [])
            pivot    = self.osint.get("pivot", {})
            ent      = self.osint.get("extracted_entities", {})

            def _conf_badge(r):
                lvl = r.get("confidence", "low")
                cls = {"high": "conf-high", "medium": "conf-med", "low": "conf-low"}.get(lvl, "conf-low")
                return f"<span class='{cls}'>{lvl}</span>"

            def _li_list(bucket, fmt, only_conf=True):
                shown = [r for r in bucket if not only_conf or r.get("confidence") in ("high", "medium")]
                return "".join(fmt(r) for r in shown[:6]) or "<li>No results</li>"

            reddit_li = _li_list(reddit, lambda r: (
                f"<li><a href='{r.get('url','')}' target='_blank'>"
                f"r/{r.get('subreddit','')} — {r.get('title','')[:60]}</a>"
                f" <span class='by'>u/{r.get('author','')}</span></li>"
            ), only_conf=False)
            github_li = _li_list(github, lambda g: (
                f"<li><a href='{g.get('url','')}' target='_blank'>"
                f"{g.get('repo','')} / {g.get('file','')}</a></li>"
            ), only_conf=False)
            web_li = _li_list(web, lambda r: (
                f"<li>{_conf_badge(r)} <a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:70]}</a></li>"
            ))
            twitter_li = _li_list(twitter, lambda r: (
                f"<li>{_conf_badge(r)} <a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:60]}</a></li>"
            ))
            telegram_li = _li_list(telegram, lambda r: (
                f"<li>{_conf_badge(r)} <a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:60]}</a></li>"
            ))
            reddit_c_li = _li_list(reddit_c, lambda r: (
                f"<li>{_conf_badge(r)} <a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:60]}</a></li>"
            ))
            dorks_li = _li_list(dorks, lambda r: (
                f"<li>{_conf_badge(r)} <span class='dork-tag'>[{r.get('dork','')}]</span> "
                f"<a href='{r.get('url','')}' target='_blank'>{r.get('title','')[:55]}</a></li>"
            ))
            onchain_li = "".join(
                f"<li><span class='dork-tag'>[{o.get('source','')}]</span> {o.get('text','')[:120]}</li>"
                for o in onchain if "error" not in o
            ) or "<li>No on-chain comments/tags found</li>"

            emails    = ", ".join(ent.get("emails", [])[:5])    or "—"
            phones    = ", ".join(ent.get("phones", [])[:3])    or "—"
            usernames = ", ".join(ent.get("usernames", [])[:6]) or "—"
            telegrams = ", ".join(ent.get("telegrams", [])[:4]) or "—"

            osint_html = f"""
<div class="card">
  <h2>🔍 OSINT Findings</h2>
  <div class="grid4">
    <div class="stat"><span>{len(web)}</span>Web</div>
    <div class="stat"><span>{len(twitter)}</span>Twitter/X</div>
    <div class="stat"><span>{len(telegram)}</span>Telegram</div>
    <div class="stat"><span>{len(reddit) + len(reddit_c)}</span>Reddit</div>
    <div class="stat"><span>{len(github)}</span>GitHub</div>
    <div class="stat"><span>{len(btalk)}</span>BitcoinTalk</div>
    <div class="stat"><span>{len(dorks)}</span>Dorks</div>
    <div class="stat"><span>{len(onchain)}</span>On-chain tags</div>
  </div>

  <h3>Extracted identifiers <small>(found in public posts near this address)</small></h3>
  <table>
    <tr><th>Type</th><th>Values</th></tr>
    <tr><td>📧 Emails</td><td>{emails}</td></tr>
    <tr><td>📞 Phones</td><td>{phones}</td></tr>
    <tr><td>👤 Usernames</td><td>{usernames}</td></tr>
    <tr><td>✈️ Telegram</td><td>{telegrams}</td></tr>
  </table>

  <h3>On-chain public tags/comments <small>(Etherscan / WalletExplorer, best-effort)</small></h3>
  <ul>{onchain_li}</ul>

  <h3>Web mentions</h3><ul>{web_li}</ul>
  <h3>Twitter/X</h3><ul>{twitter_li}</ul>
  <h3>Telegram</h3><ul>{telegram_li}</ul>
  <h3>Reddit posts</h3><ul>{reddit_li}</ul>
  <h3>Reddit comments</h3><ul>{reddit_c_li}</ul>
  <h3>GitHub</h3><ul>{github_li}</ul>
  <h3>Dorks <small>(leaked docs, paste sites, alt code hosts)</small></h3><ul>{dorks_li}</ul>
</div>"""

            # ── Identity pivot card ──
            if pivot.get("usernames") or pivot.get("emails"):
                rows = ""
                for username, checks in pivot.get("usernames", {}).items():
                    gh, kb, tg = checks.get("github", {}), checks.get("keybase", {}), checks.get("telegram", {})
                    if gh.get("exists"):
                        rows += f"<tr><td>@{username}</td><td>GitHub</td><td>✓ <a href='{gh.get('url','')}' target='_blank'>{gh.get('url','')}</a> ({gh.get('public_repos',0)} repos)</td></tr>"
                    if kb.get("exists"):
                        rows += f"<tr><td>@{username}</td><td>Keybase</td><td>✓ linked: {', '.join(kb.get('linked_proofs', [])) or '—'}</td></tr>"
                    if tg.get("exists"):
                        rows += f"<tr><td>@{username}</td><td>Telegram</td><td>✓ <a href='{tg.get('url','')}' target='_blank'>{tg.get('url','')}</a></td></tr>"
                    if not any((gh.get("exists"), kb.get("exists"), tg.get("exists"))):
                        rows += f"<tr><td>@{username}</td><td>—</td><td class='dim'>no matches on checked platforms</td></tr>"
                for email, checks in pivot.get("emails", {}).items():
                    gr, gc = checks.get("gravatar", {}), checks.get("github_commits", {})
                    if gr.get("exists"):
                        rows += f"<tr><td>{email}</td><td>Gravatar</td><td>✓ {gr.get('display_name','')} — <a href='{gr.get('profile_url','')}' target='_blank'>{gr.get('profile_url','')}</a></td></tr>"
                    if gc.get("exists"):
                        rows += f"<tr><td>{email}</td><td>GitHub commits</td><td>✓ {gc.get('github_username','')} ({gc.get('commits_found',0)} commit(s))</td></tr>"
                    if not any((gr.get("exists"), gc.get("exists"))):
                        rows += f"<tr><td>{email}</td><td>—</td><td class='dim'>no matches on checked platforms</td></tr>"

                pivot_html = f"""
<div class="card">
  <h2>🧬 Identity Pivot — Cross-platform Footprint</h2>
  <table><tr><th>Identifier</th><th>Platform</th><th>Result</th></tr>{rows}</table>
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
.conf-high{{background:#0f1c14;color:#86efac;border:1px solid #166534;padding:1px 6px;border-radius:8px;font-size:10px;margin-right:4px}}
.conf-med{{background:#1a1200;color:#fcd34d;border:1px solid #78350f;padding:1px 6px;border-radius:8px;font-size:10px;margin-right:4px}}
.conf-low{{background:#1c0f0f;color:#fca5a5;border:1px solid #7f1d1d;padding:1px 6px;border-radius:8px;font-size:10px;margin-right:4px}}
.dork-tag{{color:#818cf8;font-size:10px;font-weight:600}}
.dim{{color:#64748b;font-size:11px}}
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

{pivot_html}

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
