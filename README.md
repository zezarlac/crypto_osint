# CryptoWalletOSINT 🔍

> **For academic / research use only.**  
> All data comes from public blockchains and publicly accessible sources.

A Python CLI tool that performs OSINT analysis on cryptocurrency wallet addresses:
transaction history, fund flows, entity identification, and surface-level identity correlation from public web data.

---

## Features

| Module | What it does |
|--------|-------------|
| **Detector** | Auto-detects chain from address format (BTC, ETH, LTC, DOGE, TRX) |
| **Blockchain** | Fetches balance, full TX history, input/output addresses via free public APIs |
| **OSINT** | Searches DuckDuckGo, Reddit, GitHub, BitcoinTalk for address mentions |
| **Entity extract** | Pulls emails, phone patterns, usernames found *publicly posted* near the address |
| **Graph** | Builds a directed NetworkX transaction graph and renders it as PNG |
| **Reports** | Exports JSON + TXT + HTML reports per analysis run |

---

## Setup

```bash
git clone https://github.com/yourusername/crypto-wallet-osint
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
# Basic blockchain scan (no OSINT, no graph)
python main.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf

# Full OSINT + graph + all report formats
python main.py 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe --osint --graph

# TRX wallet, JSON output only, 100 transactions
python main.py TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7 --osint --output json --max-tx 100

# Suppress banner (for scripting)
python main.py <address> --no-banner --output json
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `address` | required | Wallet address to analyse |
| `--osint` | off | Enable web OSINT (DDG, Reddit, GitHub, BitcoinTalk) |
| `--graph` | off | Save transaction graph as PNG |
| `--depth N` | 2 | Graph traversal depth |
| `--max-tx N` | 50 | Max transactions to fetch |
| `--output` | all | `json` / `txt` / `html` / `all` |
| `--no-banner` | off | Skip ASCII art banner |

---

## APIs used

| Service | Chain | Key needed |
|---------|-------|-----------|
| blockchain.info | Bitcoin | No |
| Etherscan | Ethereum | Yes (free) |
| Tronscan | Tron | No |
| Blockchair | LTC, DOGE | No (rate-limited) |
| Reddit JSON | OSINT | No |
| GitHub API | OSINT | No / optional token |
| DuckDuckGo HTML | OSINT | No |
| BitcoinTalk | OSINT | No |

---

## Output

Every run creates `reports/<address8>_<timestamp>/`:
```
reports/
└── 1A1zP1eP_20240115_143022/
    ├── report.json   ← machine-readable full dump
    ├── report.txt    ← human-readable summary
    └── report.html   ← interactive HTML report
reports/
└── graph_1A1zP1eP5Q.png  ← transaction graph (if --graph)
```

---

## Project structure

```
crypto_osint/
├── main.py           ← CLI entry point
├── config.py         ← API keys & settings
├── requirements.txt
├── .env              ← your keys (not committed)
└── modules/
    ├── detector.py   ← chain detection by regex
    ├── blockchain.py ← BTC / ETH / TRX / LTC / DOGE APIs
    ├── osint.py      ← web OSINT + entity extraction
    ├── graph.py      ← NetworkX graph + PNG render
    └── report.py     ← JSON / TXT / HTML reports
```

---

## Sample output

Transaction graph (Bitcoin — demo data):

![Transaction Graph](docs_graph_sample.png)

---

## Legal & Ethical Notice

- This tool queries **only public APIs and publicly accessible web pages**.
- Blockchain data is **inherently public** by design.
- OSINT results reflect information **voluntarily published** by users online.
- Do not use this tool to harass, stalk, or harm individuals.
- Comply with the laws of your jurisdiction.
- Intended for academic research, fraud investigation, and security education.
