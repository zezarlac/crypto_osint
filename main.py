#!/usr/bin/env python3
"""
CryptoWalletOSINT — main.py
Cryptocurrency wallet OSINT analysis tool.
For educational and research use only.

Usage:
  python main.py <address> [options]

Examples:
  python main.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf
  python main.py 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe --osint --graph
  python main.py 0xAddr --depth 3 --graph                       (multi-hop trace)
  python main.py 0xAddrA --compare 0xAddrB 0xAddrC               (compare wallets)
"""

import argparse
import sys
import os

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from modules.detector import detect_chain, supported_chains
from modules.blockchain import BlockchainFetcher
from modules.osint import OSINTSearcher
from modules.graph import TransactionGraph
from modules.report import ReportGenerator
from modules.screening import Screener
from modules.tracer import MultiHopTracer
from modules.comparator import WalletComparator

# ─────────────────────────────────────────────────────────────
console = Console()

BANNER = """\
[bold purple]
  ██████╗██████╗ ██╗   ██╗██████╗ ████████╗ ██████╗     ██████╗ ███████╗██╗███╗   ██╗████████╗
 ██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝██╔═══██╗   ██╔═══██╗██╔════╝██║████╗  ██║╚══██╔══╝
 ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   ██║   ██║   ██║   ██║███████╗██║██╔██╗ ██║   ██║
 ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   ██║   ██║   ██║   ██║╚════██║██║██║╚██╗██║   ██║
 ╚██████╗██║  ██║   ██║   ██║        ██║   ╚██████╔╝   ╚██████╔╝███████║██║██║ ╚████║   ██║
  ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝    ╚═════╝     ╚═════╝ ╚══════╝╚═╝╚═╝  ╚═══╝   ╚═╝[/bold purple]
[dim]              Cryptocurrency Wallet OSINT Tool by zezarlac ·  Educational Use Only[/dim]
"""


# ─────────────────────────────────────────────────────────────
def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CryptoWalletOSINT — cryptocurrency wallet analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Supported chains: " + ", ".join(supported_chains()) + "\n\n"
            "Examples:\n"
            "  python main.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf\n"
            "  python main.py 0x... --osint --graph\n"
            "  python main.py 0x... --depth 3 --graph        (trace 3 hops)\n"
            "  python main.py 0xA --compare 0xB 0xC           (compare wallets)"
        ),
    )
    p.add_argument("address",
                   help="Wallet address to analyze")
    p.add_argument("--max-tx", type=int, default=50, metavar="N",
                   help="Max transactions to fetch (default: 50)")
    p.add_argument("--osint", action="store_true",
                   help="Enable web OSINT searches (Reddit, GitHub, DDG, BitcoinTalk)")
    p.add_argument("--graph", action="store_true",
                   help="Build & save transaction graph image")
    p.add_argument("--depth", type=int, default=1, metavar="N",
                   help="Hops to trace beyond the target (1-3). >1 fetches "
                        "transaction data for related addresses too — more "
                        "API calls, deeper investigation. Default: 1")
    p.add_argument("--compare", nargs="+", metavar="ADDR", default=None,
                   help="One or more additional addresses to compare against "
                        "the primary address, looking for shared counterparties")
    p.add_argument("--output", choices=["json", "txt", "html", "all"], default="all",
                   help="Report format (default: all)")
    p.add_argument("--no-banner", action="store_true",
                   help="Suppress ASCII banner")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────
def print_wallet_table(data: dict):
    chain = data.get("chain", "unknown")
    t = Table(box=box.ROUNDED, border_style="purple", show_header=False)
    t.add_column("K", style="cyan", width=22)
    t.add_column("V")

    t.add_row("Chain",    chain.upper())
    t.add_row("Address",  data.get("address", "N/A"))

    if chain == "bitcoin":
        t.add_row("Balance",        f"{data.get('balance_btc', 0):.8f} BTC")
        t.add_row("Total received", f"{data.get('total_received_btc', 0):.8f} BTC")
        t.add_row("Total sent",     f"{data.get('total_sent_btc', 0):.8f} BTC")
    elif chain == "ethereum":
        t.add_row("Balance", f"{data.get('balance_eth', 0):.6f} ETH")
    elif chain == "tron":
        t.add_row("Balance", f"{data.get('balance_trx', 0):.2f} TRX")
    else:
        t.add_row("Balance", str(data.get("balance", 0)))

    t.add_row("Transactions", str(data.get("tx_count", 0)))
    label = data.get("label", "")
    if label:
        t.add_row("Entity / Label", f"[yellow]{label}[/yellow]")
    if "error" in data:
        t.add_row("⚠ API Error", f"[red]{data['error']}[/red]")

    console.print(t)


def print_osint_table(osint: dict):
    ent    = osint.get("extracted_entities", {})
    web    = osint.get("web", [])
    reddit = osint.get("reddit", [])
    github = osint.get("github", [])
    btalk  = osint.get("bitcointalk", [])

    t = Table(title="OSINT Findings", box=box.ROUNDED, border_style="blue")
    t.add_column("Source",   style="cyan", width=16)
    t.add_column("Hits",     width=6)
    t.add_column("Top result", style="dim")

    t.add_row("Web (DDG)",   str(len(web)),    web[0].get("title", "—")[:55]    if web    else "—")
    t.add_row("Reddit",      str(len(reddit)), f"r/{reddit[0].get('subreddit','')} — {reddit[0].get('title','')[:40]}" if reddit else "—")
    t.add_row("GitHub",      str(len(github)), github[0].get("repo", "—")[:55]  if github else "—")
    t.add_row("BitcoinTalk", str(len(btalk)),  btalk[0].get("title", "—")[:55]  if btalk  else "—")

    emails = ent.get("emails", [])
    phones = ent.get("phones", [])
    users  = ent.get("usernames", [])
    tgrams = ent.get("telegrams", [])

    if emails:
        t.add_row("📧 Emails",    str(len(emails)), ", ".join(emails[:3]))
    if phones:
        t.add_row("📞 Phones",    str(len(phones)), ", ".join(phones[:2]))
    if users:
        t.add_row("👤 Usernames", str(len(users)),  ", ".join(users[:4]))
    if tgrams:
        t.add_row("✈️ Telegram",  str(len(tgrams)), ", ".join(tgrams[:3]))

    console.print(t)


def print_screening_table(screening: dict, screener: Screener):
    if not screening:
        console.print("[green]✓[/green]  No sanctions/mixer matches found\n")
        return

    t = Table(
        title=f"🚨 {len(screening)} SANCTIONS / MIXER WATCHLIST MATCH(ES)",
        box=box.HEAVY, border_style="red", title_style="bold red",
    )
    t.add_column("Address", style="yellow", overflow="fold")
    t.add_column("Entity")
    t.add_column("Category")
    t.add_column("Program / Date", style="dim")

    for addr, entry in screening.items():
        t.add_row(
            addr,
            entry.get("entity", ""),
            ", ".join(entry.get("category", [])),
            f"{entry.get('program','')}\n{entry.get('date','')}",
        )
    console.print(t)
    meta = screener.stats()
    console.print(
        f"[dim]  Screened against {meta['total_entries']} curated OFAC SDN "
        f"entries (updated {meta['last_updated']}) — not the full list.[/dim]\n"
    )


def print_trace_summary(trace: dict):
    t = Table(box=box.ROUNDED, border_style="cyan", show_header=False)
    t.add_column("K", style="cyan", width=22)
    t.add_column("V")
    t.add_row("Depth",            f"{trace.get('depth', 1)} hop(s)")
    t.add_row("Total addresses",  str(trace.get("total_addresses", 0)))
    for hop, count in trace.get("hop_counts", {}).items():
        t.add_row(f"  Hop {hop}", f"{count} new address(es)")
    if trace.get("flagged"):
        t.add_row("⚠ Flagged", f"[red]{len(trace['flagged'])} address(es)[/red]")
    console.print(t)


def print_comparison_table(result: dict):
    t = Table(
        title=f"🔗 Wallet Comparison — {len(result['wallets'])} wallets",
        box=box.ROUNDED, border_style="magenta",
    )
    t.add_column("Wallet", overflow="fold")
    t.add_column("Counterparties", width=14)
    for w in result["wallets"]:
        t.add_row(w, str(len(result["counterparties"].get(w, []))))
    console.print(t)

    if result["shared"]:
        st = Table(
            title=f"⚠ {result['shared_count']} SHARED COUNTERPARTY ADDRESS(ES)",
            box=box.HEAVY, border_style="red", title_style="bold red",
        )
        st.add_column("Shared address", overflow="fold")
        st.add_column("Shared by")
        for addr, owners in result["shared"].items():
            st.add_row(addr, "\n".join(owners))
        console.print(st)
        console.print(
            "[yellow]  → Possible common ownership between these wallets.[/yellow]\n"
        )
    else:
        console.print("[green]✓[/green]  No shared counterparties — no evidence of common ownership\n")


# ─────────────────────────────────────────────────────────────
def run_compare(primary_address: str, primary_chain: str, primary_data: dict,
                 compare_addrs: list, fetcher: BlockchainFetcher, max_tx: int):
    """Fetch the compare addresses, group by chain, and run WalletComparator."""
    console.print("[yellow]⟳[/yellow]  Fetching wallets for comparison…")

    wallets = {primary_address: primary_data}
    for addr in compare_addrs:
        chain = detect_chain(addr)
        if not chain:
            console.print(f"[red]  ✗ Skipping unrecognized address: {addr}[/red]")
            continue
        wallets[addr] = fetcher.fetch(addr, chain, max_tx=max_tx)

    # Group by chain — comparison only makes sense within the same chain
    by_chain = {}
    for addr, wd in wallets.items():
        by_chain.setdefault(wd.get("chain", "?"), {})[addr] = wd

    for chain, group in by_chain.items():
        if len(group) < 2:
            console.print(
                f"[dim]  ({chain.upper()}: only 1 address — nothing to compare)[/dim]"
            )
            continue
        console.print(f"\n[bold]Comparing {len(group)} {chain.upper()} wallets…[/bold]")
        comparator = WalletComparator(group)
        result = comparator.compare()
        print_comparison_table(result)
        comparator.generate_report(result, out_dir="reports")

    if len(by_chain) > 1:
        console.print(
            "[dim]  Note: addresses on different chains were grouped and "
            "compared separately (shared-counterparty analysis only applies "
            "within the same chain).[/dim]\n"
        )


# ─────────────────────────────────────────────────────────────
def main():
    args = build_args()

    if not args.no_banner:
        console.print(BANNER)

    # ── Step 1: Detect chain ──────────────────────────────────
    with console.status("[yellow]Detecting blockchain…[/yellow]"):
        chain = detect_chain(args.address)

    if not chain:
        console.print(
            f"[red]✗ Unrecognized address format:[/red] {args.address}\n"
            f"[dim]Supported chains: {', '.join(supported_chains())}[/dim]"
        )
        sys.exit(1)

    console.print(f"[green]✓[/green] Chain detected → [bold]{chain.upper()}[/bold]")

    # ── Step 2: Blockchain data ───────────────────────────────
    console.print("[yellow]⟳[/yellow]  Fetching blockchain data…")
    fetcher     = BlockchainFetcher()
    wallet_data = fetcher.fetch(args.address, chain, max_tx=args.max_tx)

    if "error" not in wallet_data:
        console.print("[green]✓[/green]  Blockchain data fetched")

    console.print()
    print_wallet_table(wallet_data)
    console.print()

    # ── Step 3: Screening (always on — local lookup, zero API cost) ──
    console.print("[bold]Screening against sanctions/mixer watchlist…[/bold]")
    screener   = Screener()
    addr_set   = {args.address}
    from modules.utils import extract_counterparties
    addr_set  |= extract_counterparties(args.address, wallet_data)
    screening  = screener.check_many(addr_set)
    print_screening_table(screening, screener)

    # ── Step 4: Multi-hop trace (depth > 1) ───────────────────
    trace_result = {}
    if args.depth > 1:
        depth = min(args.depth, 3)
        console.print(f"[yellow]⟳[/yellow]  Tracing {depth} hops (this calls the API "
                       f"for each related address, may take a while)…")
        tracer = MultiHopTracer(fetcher=fetcher)
        trace_result = tracer.trace(
            args.address, chain, depth=depth, root_wallet_data=wallet_data,
            progress_cb=lambda msg: console.print(f"  [dim]{msg}[/dim]"),
        )
        console.print("[green]✓[/green]  Multi-hop trace complete\n")
        print_trace_summary(trace_result)
        if trace_result.get("flagged"):
            console.print()
            print_screening_table(trace_result["flagged"], screener)
        console.print()

    # ── Step 5: OSINT ─────────────────────────────────────────
    osint_data = {}
    if args.osint:
        console.print("[yellow]⟳[/yellow]  Running OSINT searches (may take ~10 s)…")
        searcher   = OSINTSearcher()
        osint_data = searcher.search_all(args.address)
        console.print("[green]✓[/green]  OSINT searches complete\n")
        print_osint_table(osint_data)
        console.print()

    # ── Step 6: Transaction graph ─────────────────────────────
    graph_path = ""
    if args.graph:
        console.print("[yellow]⟳[/yellow]  Building transaction graph…")
        if trace_result:
            grapher = TransactionGraph.from_trace(trace_result)
        else:
            grapher = TransactionGraph(wallet_data, depth=1)
            grapher.build()

        stats      = grapher.get_stats()
        graph_path = grapher.visualize(args.address, out_dir="reports")
        flag_note  = f" · [red]{len(stats['flagged'])} flagged[/red]" if stats["flagged"] else ""
        console.print(
            f"[green]✓[/green]  Graph: "
            f"[bold]{stats['nodes']}[/bold] nodes · "
            f"[bold]{stats['edges']}[/bold] edges{flag_note} → {graph_path}"
        )
        console.print()

    # ── Step 7: Wallet comparison ──────────────────────────────
    if args.compare:
        run_compare(args.address, chain, wallet_data, args.compare, fetcher, args.max_tx)

    # ── Step 8: Reports ────────────────────────────────────────
    console.print("[yellow]⟳[/yellow]  Generating reports…")
    reporter = ReportGenerator(args.address, chain, wallet_data, osint_data, trace_result)
    paths    = reporter.generate(args.output)
    console.print()

    # ── Done ──────────────────────────────────────────────────
    summary_lines = [f"[bold green]✓ Analysis complete — {chain.upper()}[/bold green]"]
    summary_lines.append(f"   Address  : {args.address}")
    if trace_result:
        summary_lines.append(f"   Trace    : depth {trace_result.get('depth')} · "
                              f"{trace_result.get('total_addresses')} addresses")
    if graph_path:
        summary_lines.append(f"   Graph    : {graph_path}")
    if screening:
        summary_lines.append(f"   [red]⚠ Watchlist : {len(screening)} match(es)[/red]")
    summary_lines.append(f"   Reports  : {os.path.dirname(paths[0]) if paths else 'reports/'}")

    console.print(Panel("\n".join(summary_lines), border_style="green"))


if __name__ == "__main__":
    main()
