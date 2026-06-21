"""
modules/utils.py — CryptoWalletOSINT
Shared helpers for extracting counterparties/edges from wallet
transaction data. Each chain's transaction format is parsed
HERE ONLY, so graph.py, tracer.py, comparator.py and report.py
all stay in sync automatically.
"""


def extract_counterparties(address: str, wallet_data: dict) -> set:
    """Return the set of all addresses `address` has transacted with."""
    chain = wallet_data.get("chain", "")
    txs   = wallet_data.get("transactions", [])
    peers = set()

    if chain == "bitcoin":
        for tx in txs:
            for inp in tx.get("inputs", []):
                if inp and inp not in ("unknown", "coinbase", address):
                    peers.add(inp)
            for out in tx.get("outputs", []):
                a = out.get("address", "")
                if a and a not in ("unknown", address):
                    peers.add(a)
    elif chain in ("ethereum", "tron"):
        addr_cmp = address.lower() if chain == "ethereum" else address
        for tx in txs:
            frm = tx.get("from", "") or ""
            to  = tx.get("to", "")   or ""
            f_cmp = frm.lower() if chain == "ethereum" else frm
            t_cmp = to.lower()  if chain == "ethereum" else to
            if f_cmp and f_cmp != addr_cmp:
                peers.add(frm)
            if t_cmp and t_cmp != addr_cmp:
                peers.add(to)
    return peers


def extract_edges(address: str, wallet_data: dict, hop: int = 1) -> list:
    """
    Turn a wallet's transactions into a list of directed edge dicts:
    {"from": ..., "to": ..., "txid": ..., "value": ..., "hop": ...}
    """
    chain = wallet_data.get("chain", "")
    txs   = wallet_data.get("transactions", [])
    edges = []

    if chain == "bitcoin":
        for tx in txs:
            txid = tx.get("txid", "?")
            for inp in tx.get("inputs", []):
                if inp and inp not in ("unknown", "coinbase", address):
                    edges.append({"from": inp, "to": address, "txid": txid,
                                  "value": 0, "hop": hop})
            for out in tx.get("outputs", []):
                a = out.get("address", "")
                if a and a not in ("unknown", address):
                    edges.append({"from": address, "to": a, "txid": txid,
                                  "value": out.get("value_btc", 0), "hop": hop})
    elif chain in ("ethereum", "tron"):
        val_key  = "value_eth" if chain == "ethereum" else "value_trx"
        addr_cmp = address.lower() if chain == "ethereum" else address
        for tx in txs:
            frm = tx.get("from", "") or ""
            to  = tx.get("to", "")   or ""
            f_cmp = frm.lower() if chain == "ethereum" else frm
            t_cmp = to.lower()  if chain == "ethereum" else to
            txid  = tx.get("txid", "?")
            val   = tx.get(val_key, 0)
            if f_cmp and f_cmp != addr_cmp:
                edges.append({"from": frm, "to": address, "txid": txid, "value": val, "hop": hop})
            if t_cmp and t_cmp != addr_cmp:
                edges.append({"from": address, "to": to, "txid": txid, "value": val, "hop": hop})
    return edges
