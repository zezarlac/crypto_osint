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
  python main.py bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq --osint --output html
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
[dim]              Cryptocurrency Wallet OSINT Tool  ·  Educational Use Only[/dim]
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
            "  python main.py 0x... --osint --graph --depth 3\n"
            "  python main.py T... --osint --output json"
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
    p.add_argument("--depth", type=int, default=2, metavar="N",
                   help="Graph depth for multi-hop traversal (default: 2)")
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
        t.add_row("Balance",       f"{data.get('balance_btc', 0):.8f} BTC")
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

    t.add_row("Web (DDG)",    str(len(web)),    web[0].get("title", "—")[:55]    if web    else "—")
    t.add_row("Reddit",       str(len(reddit)), f"r/{reddit[0].get('subreddit','')} — {reddit[0].get('title','')[:40]}" if reddit else "—")
    t.add_row("GitHub",       str(len(github)), github[0].get("repo", "—")[:55]  if github else "—")
    t.add_row("BitcoinTalk",  str(len(btalk)),  btalk[0].get("title", "—")[:55]  if btalk  else "—")

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

    if wallet_data.get("tx_count", -1) == -1 and "error" not in wallet_data:
        console.print("[yellow]  ⚠ No transaction data returned (empty wallet?)[/yellow]")
    elif "error" not in wallet_data:
        console.print("[green]✓[/green]  Blockchain data fetched")

    console.print()
    print_wallet_table(wallet_data)
    console.print()

    # ── Step 3: OSINT ─────────────────────────────────────────
    osint_data = {}
    if args.osint:
        console.print("[yellow]⟳[/yellow]  Running OSINT searches (may take ~10 s)…")
        searcher   = OSINTSearcher()
        osint_data = searcher.search_all(args.address)
        console.print("[green]✓[/green]  OSINT searches complete\n")
        print_osint_table(osint_data)
        console.print()

    # ── Step 4: Transaction graph ─────────────────────────────
    graph_path = ""
    if args.graph:
        txs = wallet_data.get("transactions", [])
        if txs:
            console.print("[yellow]⟳[/yellow]  Building transaction graph…")
            grapher    = TransactionGraph(wallet_data, depth=args.depth)
            grapher.build()
            stats      = grapher.get_stats()
            graph_path = grapher.visualize(args.address, out_dir="reports")
            console.print(
                f"[green]✓[/green]  Graph: "
                f"[bold]{stats['nodes']}[/bold] nodes · "
                f"[bold]{stats['edges']}[/bold] edges → {graph_path}"
            )
            console.print()
        else:
            console.print("[dim]  (no transactions to graph)[/dim]\n")

    # ── Step 5: Reports ───────────────────────────────────────
    console.print("[yellow]⟳[/yellow]  Generating reports…")
    reporter = ReportGenerator(args.address, chain, wallet_data, osint_data)
    paths    = reporter.generate(args.output)
    console.print()

    # ── Done ──────────────────────────────────────────────────
    summary_lines = [f"[bold green]✓ Analysis complete — {chain.upper()}[/bold green]"]
    summary_lines.append(f"   Address  : {args.address}")
    if graph_path:
        summary_lines.append(f"   Graph    : {graph_path}")
    summary_lines.append(f"   Reports  : {os.path.dirname(paths[0]) if paths else 'reports/'}")

    console.print(Panel("\n".join(summary_lines), border_style="green"))


if __name__ == "__main__":
    main()
