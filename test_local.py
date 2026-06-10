#!/usr/bin/env python3
"""
test_local.py — CryptoWalletOSINT
Validates all modules that don't require network access.
Run before pushing: python test_local.py
"""

import sys
import os
import json
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
import tempfile, shutil
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
