"""
config.py — CryptoWalletOSINT
API keys and global settings.

HOW TO SET KEYS:
  Option A: Create a .env file with the variables below.
  Option B: Export them in your shell:
            export ETHERSCAN_API_KEY="your_key"
  Option C: Edit the fallback values directly (not recommended for sharing).

Free keys:
  Etherscan → https://etherscan.io/register  (5 req/s, free)
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── API Keys ──────────────────────────────────────────────
    ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "YourApiKeyToken")
    GITHUB_TOKEN      = os.getenv("GITHUB_TOKEN", "")        # optional, raises rate limit

    # ── Request settings ──────────────────────────────────────
    TIMEOUT           = 15      # seconds per request
    RATE_DELAY        = 0.30    # seconds between consecutive API calls

    # ── Analysis defaults ─────────────────────────────────────
    MAX_TX            = 50      # default max transactions to fetch
    GRAPH_DEPTH       = 2       # default hop depth for graph

    # ── Output ───────────────────────────────────────────────
    OUTPUT_DIR        = "reports"
