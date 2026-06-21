# CryptoWalletOSINT 🔍

> **For academic / research use only.**
> All data comes from public blockchains and publicly accessible sources.

A Python CLI tool that performs OSINT analysis on cryptocurrency wallet addresses:
transaction history, fund flows, multi-hop tracing, sanctions/mixer screening,
wallet comparison, and surface-level identity correlation from public web data.

---

## Features

| Module | What it does |
|--------|-------------|
| **Detector** | Auto-detects chain from address format (BTC, ETH, LTC, DOGE, TRX) |
| **Blockchain** | Fetches balance, full TX history, input/output addresses via free public APIs |
| **OSINT** | Searches DuckDuckGo, Twitter/X, Telegram, Reddit (posts+comments), GitHub, BitcoinTalk, plus Google-dork-style sweeps and on-chain public tags |
| **Identity pivot** | Cross-platform check on found usernames/emails — GitHub, Keybase, Telegram, Gravatar, GitHub commit authorship |
| **Entity extract** | Pulls emails, phone patterns, usernames found *publicly posted* near the address, confidence-scored against literal address matches |
| **Multi-hop tracer** | Follows funds 2-3 hops beyond the target, prioritizing the largest transfers |
| **Sanctions/mixer screening** | Flags addresses against a curated OFAC SDN sample (Tornado Cash, Blender.io, Garantex, Hydra Market) — runs automatically, no API cost |
| **Wallet comparator** | Compares 2+ wallets and finds shared counterparties — evidence of common ownership |
| **Graph** | Directed NetworkX transaction graph rendered as PNG, color-coded by hop, flagged nodes highlighted |
| **Reports** | Exports JSON + TXT + HTML reports per analysis run |

---

## Setup

```bash
git clone https://github.com/zezarlac/crypto_osint
cd crypto-wallet-osint
pip install -r requirements.txt
```

**API keys** (create a `.env` file):
```env
ETHERSCAN_API_KEY=your_free_key_here   # etherscan.io → Register → API Keys
GITHUB_TOKEN=optional_token            # raises GitHub search rate limit
```

Get a free Etherscan key at <https://etherscan.io/register> → API Keys.

---

## Usage

```bash
# Basic blockchain scan (1 hop, no OSINT, no graph)
python main.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf

# Full OSINT + graph + all report formats
python main.py 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe --osint --graph

# Trace funds 3 hops downstream and graph the result
python main.py 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe --depth 3 --graph

# Compare 3 wallets for shared counterparties (possible common ownership)
python main.py 0xWalletA --compare 0xWalletB 0xWalletC

# Combine everything
python main.py 0xAddr --osint --graph --depth 2 --compare 0xOther1 0xOther2
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `address` | required | Wallet address to analyse |
| `--osint` | off | Enable web OSINT (DDG, Reddit, GitHub, BitcoinTalk) |
| `--graph` | off | Save transaction graph as PNG |
| `--depth N` | 1 | Hops to trace beyond the target (1-3). `>1` makes extra API calls per related address |
| `--compare ADDR [ADDR ...]` | off | Additional addresses to compare against the primary one |
| `--max-tx N` | 50 | Max transactions to fetch for the primary address |
| `--output` | all | `json` / `txt` / `html` / `all` |
| `--no-banner` | off | Skip ASCII art banner |

**Sanctions/mixer screening runs automatically on every analysis** — it's a free
local lookup against the bundled watchlist (`data/sanctions_addresses.json`),
no flag needed and no extra API calls.

---

## Sanctions / Mixer Watchlist

`data/sanctions_addresses.json` ships with **32 addresses** sourced directly from
official U.S. Treasury OFAC SDN press releases:

| Entity | Chain | Category | OFAC date |
|--------|-------|----------|-----------|
| Tornado Cash | Ethereum (8 addrs) | sanctions, mixer | 2022-08-08 |
| Blender.io | Bitcoin (18 addrs) | sanctions, mixer | 2022-05-06 |
| Garantex Europe OÜ | BTC + ETH (3 addrs) | sanctions, exchange | 2022-04-05 |
| Hydra Market | Bitcoin (3 addrs) | sanctions, darknet-market | 2022-04-05 |

⚠️ **This is a small curated sample, not the full or live-updated SDN list.**
For real compliance work use the official source (treasury.gov) or a maintained
mirror like [0xB10C/ofac-sanctioned-digital-currency-addresses](https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses).
You can add your own entries to the `entries` array in the JSON file — no code
changes needed.

---

## How multi-hop tracing works

With `--depth 2` or `--depth 3`, the tracer:
1. Takes the target's direct counterparties (hop 1, already fetched).
2. Picks the **top 6 by transferred value** per hop (configurable in `modules/tracer.py`)
   — this keeps API usage bounded instead of exploding combinatorially.
3. Fetches each one's transactions and repeats for the next hop.
4. Screens every discovered address against the sanctions/mixer watchlist.

**Limitation:** for Bitcoin, the input side of a transaction doesn't carry a
clean per-address value in the data this tool fetches, so hop expansion is
weighted toward **outgoing** transfers (where the target's funds *went*).

---

## How wallet comparison works

`--compare` fetches each address, extracts its full set of direct counterparties,
and reports any address that appears as a counterparty of **2 or more** of the
wallets being compared. A shared counterparty (e.g. both wallets funding the
same exchange deposit address) is a strong signal of common ownership.
Addresses on different chains are grouped and compared separately.

---

## OSINT capabilities in detail

`--osint` runs a multi-stage investigation, not just one search:

1. **Direct mentions** — DuckDuckGo (general web), Twitter/X and Telegram
   (via site-restricted queries), Reddit (both submissions and comments),
   GitHub code search, BitcoinTalk forum.
2. **Google-dork-style sweeps** — targeted operator queries for leaked
   documents (`filetype:pdf/csv/xlsx`), paste sites (Pastebin, Ghostbin,
   ControlC), and code hosts beyond GitHub (GitLab, Bitbucket, SourceForge).
3. **On-chain public tags** — best-effort scrape of Etherscan's Public Name
   Tag/comments (ETH) and WalletExplorer's service label (BTC). These are
   tied directly to the address itself rather than a fuzzy text match, so
   they're often the highest-signal source. *Page structure on these sites
   can change — this degrades to an empty result if parsing fails.*
4. **Confidence scoring** — every web/social/dork hit is tagged `high`
   (address found verbatim), `medium` (truncated/displayed form found,
   e.g. `0x1234…abcd`), or `low` (likely a loose search-engine match).
   Reports show high/medium hits prominently and note how many low-confidence
   results were filtered out (full data stays in the JSON export).
5. **Identity pivot** — once a username or email is extracted, it's checked
   against:
   - **GitHub** — profile existence + commit-author search by email
   - **Keybase** — profile + linked social proofs (often surfaces Twitter/
     Reddit/GitHub for the same person in a single call)
   - **Telegram** — public username resolution
   - **Gravatar** — public profile tied to an email's hash

   This is capped at 5 usernames / 3 emails per run to stay fast and
   within free-tier rate limits.



| Service | Chain | Key needed |
|---------|-------|-----------|
| blockchain.info | Bitcoin | No |
| Etherscan (V2) | Ethereum | Yes (free) |
| Tronscan | Tron | No |
| Blockchair | LTC, DOGE | No (rate-limited) |
| Reddit JSON | OSINT | No |
| GitHub API | OSINT | No / optional token |
| DuckDuckGo HTML | OSINT | No |
| BitcoinTalk | OSINT | No |

---

## Output

Single-wallet analysis creates `reports/<address8>_<timestamp>/`:
```
reports/
├── 1A1zP1eP_20240115_143022/
│   ├── report.json   ← machine-readable full dump (incl. screening + trace)
│   ├── report.txt    ← human-readable summary
│   └── report.html   ← interactive HTML report
├── graph_1A1zP1eP5Q.png       ← transaction graph (if --graph)
└── compare_20240115_143501/   ← wallet comparison (if --compare)
    ├── comparison.json
    ├── comparison.txt
    └── comparison.html
```

---

## Project structure

```
crypto_osint/
├── main.py             ← CLI entry point
├── config.py           ← API keys & settings
├── requirements.txt
├── .env                ← your keys (not committed)
├── data/
│   └── sanctions_addresses.json  ← curated OFAC SDN sample
└── modules/
    ├── detector.py     ← chain detection by regex
    ├── blockchain.py   ← BTC / ETH / TRX / LTC / DOGE APIs
    ├── osint.py        ← web/social OSINT + dorks + on-chain tags + entity extraction
    ├── pivot.py         ← identity pivot (username/email → cross-platform check)
    ├── screening.py    ← sanctions/mixer watchlist checks
    ├── tracer.py        ← multi-hop fund tracing
    ├── comparator.py    ← shared-counterparty wallet comparison
    ├── utils.py         ← shared tx-parsing helpers (per chain)
    ├── graph.py         ← NetworkX graph + PNG render
    └── report.py        ← JSON / TXT / HTML reports
```

---

## Sample output

Transaction graph (Bitcoin — demo data), with a sanctioned address flagged at hop 2:

![Transaction Graph](docs_graph_sample.png)

---

## Legal & Ethical Notice

- This tool queries **only public APIs and publicly accessible web pages**.
- Blockchain data is **inherently public** by design.
- OSINT results reflect information **voluntarily published** by users online.
- The sanctions watchlist is a small educational sample of public OFAC SDN data —
  not a substitute for real compliance screening.
- Do not use this tool to harass, stalk, or harm individuals.
- Comply with the laws of your jurisdiction.
- Intended for academic research, fraud investigation, and security education.
