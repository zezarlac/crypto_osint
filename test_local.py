#!/usr/bin/env python3
"""
test_local.py — CryptoWalletOSINT
Validates all modules that don't require network access.
Run before pushing: python test_local.py
"""

import sys
import os
import json
import tempfile
import shutil
from datetime import datetime

# ── colors ────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg, err=""): print(f"  {RED}✗{RESET}  {msg}" + (f" → {err}" if err else ""))
def info(msg): print(f"  {YELLOW}•{RESET}  {msg}")

passed = failed = 0


def test(name, fn):
    global passed, failed
    try:
        fn()
        ok(name)
        passed += 1
    except Exception as e:
        fail(name, str(e))
        failed += 1


# ─────────────────────────────────────────────────────────────
print(f"\n{BOLD}CryptoWalletOSINT — local tests{RESET}")
print("─" * 50)

# ── 1. Detector ───────────────────────────────────────────────
print(f"\n{BOLD}[1] Chain Detector{RESET}")
from modules.detector import detect_chain, supported_chains

ADDR_MAP = {
    # BTC formats
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na":             "bitcoin",
    "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy":               "bitcoin",
    "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq":       "bitcoin",
    # ETH
    "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe":       "ethereum",
    "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12":       "ethereum",
    # TRX
    "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7":              "tron",
    # LTC
    "LdP8Qox1VAhCzLJNqrr74YovaWYyNBUWvL":              "litecoin",
    # DOGE
    "DPohDzHNhPMmHGWFGLcVBR1AMhsNpgA5TF":              "dogecoin",
    # Invalid
    "not_a_wallet":                                     None,
    "0xSHORT":                                         None,
    "":                                                 None,
}

for addr, expected in ADDR_MAP.items():
    label = (addr[:18] + "…") if len(addr) > 18 else addr or "(empty)"
    test(
        f"detect_chain({label!r}) == {expected!r}",
        lambda a=addr, e=expected: (
            (_ := detect_chain(a)) == e or (_ for _ in ()).throw(AssertionError(f"got {_!r}"))
        ),
    )

test(
    "supported_chains() returns list",
    lambda: isinstance(supported_chains(), list) and len(supported_chains()) >= 5 or
            (_ for _ in ()).throw(AssertionError("empty or wrong type")),
)

# ── 1b. Screening (sanctions/mixer watchlist) ──────────────────
print(f"\n{BOLD}[1b] Screening — Sanctions/Mixer Watchlist{RESET}")
from modules.screening import Screener

screener = Screener()

def _screener_loads():
    stats = screener.stats()
    assert stats["total_entries"] >= 30, f"expected >=30 entries, got {stats['total_entries']}"

def _screener_finds_known_eth():
    # Real OFAC-sanctioned Tornado Cash address (sourced from ofac.treasury.gov)
    match = screener.check("0x8589427373D6D84E98730D7795D8f6f8731FDA16")
    assert match is not None
    assert match["entity"] == "Tornado Cash"
    assert "mixer" in match["category"]

def _screener_case_insensitive_eth():
    # lowercase variant should still match
    match = screener.check("0x8589427373d6d84e98730d7795d8f6f8731fda16")
    assert match is not None

def _screener_finds_known_btc():
    match = screener.check("3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3")
    assert match is not None
    assert match["entity"] == "Blender.io"

def _screener_clean_address():
    match = screener.check("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na")
    assert match is None

def _screener_check_many():
    hits = screener.check_many([
        "0x8589427373D6D84E98730D7795D8f6f8731FDA16",
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na",
    ])
    assert len(hits) == 1

test("Screener loads bundled dataset (30+ entries)", _screener_loads)
test("Screener flags known Tornado Cash address",     _screener_finds_known_eth)
test("Screener is case-insensitive for ETH",          _screener_case_insensitive_eth)
test("Screener flags known Blender.io address",       _screener_finds_known_btc)
test("Screener returns None for a clean address",     _screener_clean_address)
test("Screener.check_many() filters correctly",       _screener_check_many)

# ── 1c. Shared parsing utils ────────────────────────────────────
print(f"\n{BOLD}[1c] Utils — Transaction Parsing{RESET}")
from modules.utils import extract_counterparties, extract_edges

UTIL_BTC_WALLET = {
    "address": "TARGET_BTC", "chain": "bitcoin",
    "transactions": [
        {"txid": "tx1", "inputs": ["coinbase"],
         "outputs": [{"address": "TARGET_BTC", "value_btc": 1.0}]},
        {"txid": "tx2", "inputs": ["TARGET_BTC"],
         "outputs": [{"address": "PEER_A", "value_btc": 0.5},
                     {"address": "PEER_B", "value_btc": 0.4}]},
    ],
}

def _util_counterparties_btc():
    peers = extract_counterparties("TARGET_BTC", UTIL_BTC_WALLET)
    assert peers == {"PEER_A", "PEER_B"}, peers

def _util_edges_btc():
    edges = extract_edges("TARGET_BTC", UTIL_BTC_WALLET, hop=1)
    out_edges = [e for e in edges if e["from"] == "TARGET_BTC"]
    assert len(out_edges) == 2
    assert all(e["hop"] == 1 for e in edges)

test("extract_counterparties() — Bitcoin",  _util_counterparties_btc)
test("extract_edges() — Bitcoin",           _util_edges_btc)

# ── 1d. Comparator ───────────────────────────────────────────────
print(f"\n{BOLD}[1d] Wallet Comparator{RESET}")
from modules.comparator import WalletComparator

WALLET_A = {
    "address": "WALLET_A", "chain": "bitcoin",
    "transactions": [
        {"txid": "t1", "inputs": ["WALLET_A"],
         "outputs": [{"address": "SHARED_EXCHANGE", "value_btc": 1.0}]},
    ],
}
WALLET_B = {
    "address": "WALLET_B", "chain": "bitcoin",
    "transactions": [
        {"txid": "t2", "inputs": ["WALLET_B"],
         "outputs": [{"address": "SHARED_EXCHANGE", "value_btc": 2.0}]},
    ],
}
WALLET_C = {
    "address": "WALLET_C", "chain": "bitcoin",
    "transactions": [
        {"txid": "t3", "inputs": ["WALLET_C"],
         "outputs": [{"address": "UNRELATED_ADDR", "value_btc": 1.0}]},
    ],
}

def _comparator_finds_shared():
    comp = WalletComparator({"WALLET_A": WALLET_A, "WALLET_B": WALLET_B, "WALLET_C": WALLET_C})
    result = comp.compare()
    assert "SHARED_EXCHANGE" in result["shared"]
    assert set(result["shared"]["SHARED_EXCHANGE"]) == {"WALLET_A", "WALLET_B"}
    assert "UNRELATED_ADDR" not in result["shared"]

def _comparator_report_generates():
    comp = WalletComparator({"WALLET_A": WALLET_A, "WALLET_B": WALLET_B})
    result = comp.compare()
    tmp = tempfile.mkdtemp()
    paths = comp.generate_report(result, out_dir=tmp)
    assert os.path.exists(paths["json"])
    assert os.path.exists(paths["txt"])
    assert os.path.exists(paths["html"])
    shutil.rmtree(tmp, ignore_errors=True)

test("WalletComparator finds shared counterparty", _comparator_finds_shared)
test("WalletComparator generates JSON/TXT/HTML",   _comparator_report_generates)

# ── 1e. Multi-hop tracer (offline-safe parts only) ───────────────
print(f"\n{BOLD}[1e] Multi-hop Tracer (offline logic){RESET}")
from modules.tracer import MultiHopTracer

def _tracer_top_counterparties():
    tracer = MultiHopTracer(max_per_hop=2)
    edges = [
        {"from": "SRC", "to": "A", "value": 5.0},
        {"from": "SRC", "to": "B", "value": 1.0},
        {"from": "SRC", "to": "C", "value": 10.0},
    ]
    top = tracer._top_counterparties(edges, "SRC", visited={"SRC"})
    assert top == ["C", "A"], top   # ranked by value desc, capped at max_per_hop=2

def _tracer_excludes_visited():
    tracer = MultiHopTracer(max_per_hop=5)
    edges = [{"from": "SRC", "to": "ALREADY_SEEN", "value": 99.0}]
    top = tracer._top_counterparties(edges, "SRC", visited={"SRC", "ALREADY_SEEN"})
    assert top == []

test("Tracer ranks counterparties by value, capped", _tracer_top_counterparties)
test("Tracer excludes already-visited addresses",    _tracer_excludes_visited)

# ── 2. Report generator (no-network) ─────────────────────────
print(f"\n{BOLD}[2] Report Generator{RESET}")
from modules.report import ReportGenerator

FAKE_WALLET = {
    "address":           "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na",
    "chain":             "bitcoin",
    "balance_btc":       50.0,
    "total_received_btc": 50.0,
    "total_sent_btc":    0.0,
    "tx_count":          1,
    "transactions": [{
        "txid":    "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
        "time":    1231006505,
        "block":   0,
        "inputs":  ["coinbase"],
        "outputs": [{"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na",
                     "value_btc": 50.0, "spent": False}],
        "fee_btc": 0.0,
        "confirmed": True,
    }],
    "label": "Genesis block",
}

FAKE_OSINT = {
    "web":    [{"title": "Bitcoin Wiki — Genesis block", "url": "https://en.bitcoin.it/wiki/Genesis_block", "snippet": "The genesis block..."}],
    "reddit": [{"title": "Genesis block discussion", "subreddit": "bitcoin", "author": "satoshi", "url": "https://reddit.com/r/bitcoin/1", "score": 42, "text": "Contact: test@example.com"}],
    "github": [{"repo": "bitcoin/bitcoin", "file": "genesis.cpp", "path": "src/genesis.cpp", "url": "https://github.com/bitcoin/bitcoin", "repo_owner": "bitcoin", "repo_url": "https://github.com/bitcoin/bitcoin"}],
    "bitcointalk": [],
    "extracted_entities": {
        "emails":    ["test@example.com"],
        "phones":    ["+1 555 123 4567"],
        "usernames": ["satoshi"],
        "telegrams": [],
    },
}

# Create reports in a temp dir
tmp = tempfile.mkdtemp()

def make_reporter():
    return ReportGenerator(
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na",
        "bitcoin", FAKE_WALLET, FAKE_OSINT
    )

r = make_reporter()
# Override output dir to temp
r.out_dir = os.path.join(tmp, "test_report")
os.makedirs(r.out_dir, exist_ok=True)

test("JSON report generates without error",  lambda: r._json())
test("TXT  report generates without error",  lambda: r._txt())
test("HTML report generates without error",  lambda: r._html())

def _json_valid():
    path = os.path.join(r.out_dir, "report.json")
    with open(path) as f:
        data = json.load(f)
    assert data["meta"]["target"] == "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na"
    assert data["blockchain"]["balance_btc"] == 50.0

test("JSON report content is valid",   _json_valid)

def _txt_has_content():
    path = os.path.join(r.out_dir, "report.txt")
    txt  = open(path).read()
    assert "BITCOIN" in txt
    assert "Genesis block" in txt
    assert "test@example.com" in txt

test("TXT report contains expected data", _txt_has_content)

def _html_has_content():
    path = os.path.join(r.out_dir, "report.html")
    html = open(path).read()
    assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na" in html
    assert "Genesis block" in html

test("HTML report contains expected data", _html_has_content)

def _report_auto_screening():
    # A wallet that sent funds to a known-sanctioned mixer address
    # should show up as flagged in the report automatically.
    wallet = {
        "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na", "chain": "bitcoin",
        "balance_btc": 0, "total_received_btc": 0, "total_sent_btc": 1.0,
        "tx_count": 1,
        "transactions": [
            {"txid": "txflag", "inputs": ["1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na"],
             "outputs": [{"address": "3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3", "value_btc": 1.0}]},
        ],
    }
    rep = ReportGenerator("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na", "bitcoin", wallet)
    assert "3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3" in rep.screening
    shutil.rmtree(rep.out_dir, ignore_errors=True)

test("ReportGenerator auto-screens counterparties", _report_auto_screening)

shutil.rmtree(tmp, ignore_errors=True)

# ── 3. Graph builder (no-network, no display) ─────────────────
print(f"\n{BOLD}[3] Transaction Graph{RESET}")
from modules.graph import TransactionGraph

def _graph_bitcoin():
    g = TransactionGraph(FAKE_WALLET, depth=2)
    g.build()
    stats = g.get_stats()
    assert stats["nodes"] >= 1, "Should have at least target node"

def _graph_eth():
    fake_eth = {
        "address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
        "chain":   "ethereum",
        "balance_eth": 1.5,
        "tx_count": 2,
        "transactions": [
            {"txid": "0xabc", "from": "0x1111111111111111111111111111111111111111",
             "to":   "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
             "value_eth": 1.0, "time": 1700000000},
            {"txid": "0xdef", "from": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
             "to":   "0x2222222222222222222222222222222222222222",
             "value_eth": 0.5, "time": 1700001000},
        ],
    }
    g = TransactionGraph(fake_eth)
    g.build()
    stats = g.get_stats()
    assert stats["nodes"] == 3, f"Expected 3 nodes, got {stats['nodes']}"
    assert stats["edges"] == 2, f"Expected 2 edges, got {stats['edges']}"

def _graph_export():
    g = TransactionGraph(FAKE_WALLET)
    g.build()
    tmp_json = "/tmp/test_graph.json"
    g.export_json(tmp_json)
    with open(tmp_json) as f:
        data = json.load(f)
    assert "nodes" in data
    os.remove(tmp_json)

test("Bitcoin graph builds correctly",   _graph_bitcoin)
test("Ethereum graph nodes & edges",     _graph_eth)
test("Graph JSON export works",          _graph_export)

def _graph_from_trace():
    fake_trace = {
        "target": "TARGET_X", "chain": "bitcoin", "depth": 2,
        "nodes": {
            "TARGET_X": {"hop": 0},
            "HOP1_A":   {"hop": 1},
            "HOP2_A":   {"hop": 2},
        },
        "edges": [
            {"from": "TARGET_X", "to": "HOP1_A", "txid": "tx1", "value": 1.0, "hop": 1},
            {"from": "HOP1_A",   "to": "HOP2_A", "txid": "tx2", "value": 0.5, "hop": 2},
        ],
        "hop_counts": {1: 1, 2: 1},
        "flagged": {},
        "total_addresses": 3,
    }
    g = TransactionGraph.from_trace(fake_trace)
    stats = g.get_stats()
    assert stats["nodes"] == 3, stats["nodes"]
    assert stats["edges"] == 2, stats["edges"]
    assert g.depth == 2

def _graph_flags_sanctioned_node():
    # Tornado Cash address should be auto-flagged when building the graph
    wallet = {
        "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na", "chain": "bitcoin",
        "transactions": [
            {"txid": "tx1", "inputs": ["1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf8Na"],
             "outputs": [{"address": "3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3", "value_btc": 1.0}]},
        ],
    }
    g = TransactionGraph(wallet)
    g.build()
    stats = g.get_stats()
    assert "3K35dyL85fR9ht7UgzPfd1gLRRXQtNTqE3" in stats["flagged"]

test("TransactionGraph.from_trace() builds multi-hop graph", _graph_from_trace)
test("Graph auto-flags sanctioned addresses",                _graph_flags_sanctioned_node)

# ── 4. OSINT entity extractor (no-network) ────────────────────
print(f"\n{BOLD}[4] OSINT — Entity Extractor{RESET}")
from modules.osint import OSINTSearcher

searcher = OSINTSearcher()

def _extract_email():
    text = "Send funds to 0x123... contact me at john.doe@gmail.com for details"
    e = searcher._extract_entities(text)
    assert "john.doe@gmail.com" in e["emails"]

def _extract_phone():
    text = "Call me at +1 (555) 123-4567 to confirm the transfer"
    e = searcher._extract_entities(text)
    assert len(e["phones"]) >= 1

def _extract_username():
    text = "Follow @satoshi_nakamoto on Twitter for updates"
    e = searcher._extract_entities(text)
    assert "satoshi_nakamoto" in e["usernames"]

def _extract_telegram():
    text = "Join our group at t.me/cryptowalletosint for info"
    e = searcher._extract_entities(text)
    assert "cryptowalletosint" in e["telegrams"]

def _extract_empty():
    e = searcher._extract_entities("just some random text with no entities")
    assert e["emails"] == []

test("Extracts email from text",      _extract_email)
test("Extracts phone from text",      _extract_phone)
test("Extracts @username from text",  _extract_username)
test("Extracts t.me/ Telegram link",  _extract_telegram)
test("Returns empty lists for clean text", _extract_empty)

# ── Summary ───────────────────────────────────────────────────
total = passed + failed
print(f"\n{'─' * 50}")
print(
    f"  {BOLD}Results:{RESET}  "
    f"{GREEN}{passed} passed{RESET}  "
    f"{'  ' + RED + str(failed) + ' failed' + RESET if failed else ''}"
    f"  /  {total} total"
)
print()
if failed:
    sys.exit(1)
