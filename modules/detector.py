"""
modules/detector.py — CryptoWalletOSINT
Detects which blockchain a given wallet address belongs to
using regex patterns for each supported chain.
"""

import re
from typing import Optional

# (name, list_of_patterns)
_CHAINS = [
    ("bitcoin", [
        r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$",     # P2PKH / P2SH
        r"^bc1[a-z0-9]{6,87}$",                     # Bech32 SegWit
        r"^bc1p[a-z0-9]{6,87}$",                    # Taproot
    ]),
    ("ethereum", [
        r"^0x[a-fA-F0-9]{40}$",
    ]),
    ("litecoin", [
        r"^[LM3][a-km-zA-HJ-NP-Z1-9]{26,33}$",
        r"^ltc1[a-z0-9]{6,87}$",
    ]),
    ("dogecoin", [
        r"^D[5-9A-HJ-NP-U][1-9A-HJ-NP-Za-km-z]{32}$",
    ]),
    ("tron", [
        r"^T[a-zA-Z0-9]{33}$",
    ]),
]


def detect_chain(address: str) -> Optional[str]:
    """
    Return the blockchain name for the given address,
    or None if the format is not recognized.
    """
    for chain, patterns in _CHAINS:
        for pattern in patterns:
            if re.match(pattern, address):
                return chain
    return None


def supported_chains() -> list:
    """Return list of supported chain names."""
    return [c[0] for c in _CHAINS]
