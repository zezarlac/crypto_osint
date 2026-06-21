"""
modules/osint.py — CryptoWalletOSINT
Searches public sources for mentions of a wallet address, extracts
identifiers found nearby, and pivots from those identifiers into a
small cross-platform identity check.

Sources (all publicly accessible, no login required):
  • DuckDuckGo (HTML endpoint)            — general web mentions
  • Twitter/X, Telegram, broader Reddit   — via site-restricted
    DDG queries (reuses the same scraper)
  • Reddit public search API              — submissions
  • GitHub public code search API
  • BitcoinTalk forum search
  • Google-dork-style queries             — leaked docs, paste
    sites, alternate code hosts
  • On-chain public comments/tags         — Etherscan / WalletExplorer
    (best-effort HTML scrape; page structure can change)

Every result is tagged with a confidence level ("high"/"medium"/"low")
based on whether the address literally appears in the matched text,
to filter out loose/fuzzy search-engine matches.

Note: This module only processes information voluntarily made public
by users. It does NOT access breach databases or any private data.
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from config import Config
from modules.pivot import IdentityPivot


class OSINTSearcher:
    def __init__(self):
        self.cfg = Config()
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        })
        # Entity extraction patterns
        self._re_email    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
        self._re_phone    = re.compile(r"(?<!\d)(\+?[\d][\d\s\-\(\)]{8,17}\d)(?!\d)")
        self._re_username = re.compile(r"@([a-zA-Z0-9_]{2,50})")
        self._re_telegram = re.compile(r"t\.me/([a-zA-Z0-9_]{4,32})")

    # ── Public entry point ───────────────────────────────────────

    def search_all(self, address: str, chain: str = None) -> dict:
        """
        Run all OSINT searches, extract identifiers, and pivot from
        them into a cross-platform identity check.
        """
        web      = self._search_duckduckgo(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        reddit   = self._search_reddit(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        github   = self._search_github(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        btalk    = self._search_bitcointalk(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        twitter  = self._search_twitter(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        telegram = self._search_telegram(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        reddit_c = self._search_reddit_comments(address)
        time.sleep(self.cfg.RATE_DELAY * 5)
        dorks    = self._run_dorks(address)
        onchain  = self._search_onchain_comments(address, chain) if chain else []

        # ── Confidence tagging (literal-match filtering) ──
        for bucket in (web, twitter, telegram, reddit_c, dorks):
            for r in bucket:
                if "error" not in r:
                    r["confidence"] = self._confidence(
                        address, r.get("title", "") + " " + r.get("snippet", "")
                    )
        for r in reddit:
            if "error" not in r:
                r["confidence"] = "high"   # native API, address was the literal query
        for r in github:
            if "error" not in r:
                r["confidence"] = "high"   # code search only returns literal matches
        for r in btalk:
            if "error" not in r:
                r["confidence"] = self._confidence(address, r.get("title", ""))

        # ── Entity extraction from all gathered text ──
        corpus = []
        for r in web + twitter + telegram + reddit_c + dorks:
            corpus.append(r.get("title", "") + " " + r.get("snippet", ""))
        for r in reddit:
            corpus.append(r.get("title", "") + " " + r.get("text", "") + " u/" + r.get("author", ""))
        for r in btalk:
            corpus.append(r.get("title", ""))
        for r in onchain:
            corpus.append(r.get("text", ""))
        entities = self._extract_entities(" ".join(corpus))

        # ── Identity pivot (username/email → cross-platform check) ──
        pivot_results = {}
        if entities.get("usernames") or entities.get("emails"):
            pivoter = IdentityPivot()
            pivot_results = pivoter.pivot_all(entities)

        return {
            "web":               web,
            "reddit":            reddit,
            "github":            github,
            "bitcointalk":       btalk,
            "twitter":           twitter,
            "telegram":          telegram,
            "reddit_comments":   reddit_c,
            "dorks":             dorks,
            "onchain_comments":  onchain,
            "extracted_entities": entities,
            "pivot":             pivot_results,
        }

    # ── Generic DuckDuckGo search (reused by all site-restricted queries) ──

    def _search_ddg(self, query: str, max_results: int = 8) -> list:
        results = []
        try:
            resp = self.s.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                timeout=self.cfg.TIMEOUT,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for div in soup.find_all("div", class_="result__body")[:max_results]:
                title_a   = div.find("a", class_="result__a")
                snippet_a = div.find("a", class_="result__snippet")
                if title_a:
                    results.append({
                        "title":   title_a.get_text(strip=True),
                        "url":     title_a.get("href", ""),
                        "snippet": snippet_a.get_text(strip=True) if snippet_a else "",
                    })
        except Exception as e:
            results.append({"error": str(e)})
        return results

    def _search_duckduckgo(self, address: str) -> list:
        """General web mentions, exact-match quoted."""
        return self._search_ddg(f'"{address}"')

    # ── Expanded sources (Twitter/X, Telegram, Reddit comments) ──

    def _search_twitter(self, address: str) -> list:
        return self._search_ddg(f'"{address}" (site:twitter.com OR site:x.com)')

    def _search_telegram(self, address: str) -> list:
        return self._search_ddg(f'"{address}" site:t.me')

    def _search_reddit_comments(self, address: str) -> list:
        """
        Reddit's native search API covers submissions; this dork-style
        query surfaces comment threads too (which often contain the
        address in replies, e.g. scam reports).
        """
        return self._search_ddg(f'"{address}" site:reddit.com')

    # ── Google-dork-style sweeps ───────────────────────────────────

    def _run_dorks(self, address: str) -> list:
        """
        Targeted operator-based queries aimed at leak-style discovery:
        documents, paste sites, and code hosts beyond GitHub.
        """
        dorks = [
            ("leaked documents", f'"{address}" (filetype:pdf OR filetype:csv OR filetype:xlsx OR filetype:txt)'),
            ("paste sites",      f'"{address}" (site:pastebin.com OR site:ghostbin.com OR site:controlc.com)'),
            ("code hosting",     f'"{address}" (site:gitlab.com OR site:bitbucket.org OR site:sourceforge.net)'),
        ]
        results = []
        for label, query in dorks:
            hits = self._search_ddg(query, max_results=5)
            for h in hits:
                if "error" not in h:
                    h["dork"] = label
            results.extend(hits)
            time.sleep(self.cfg.RATE_DELAY)
        return results

    # ── Source: Reddit (native submission search) ──────────────────

    def _search_reddit(self, address: str) -> list:
        """Reddit public JSON search API — no auth required."""
        results = []
        try:
            resp = self.s.get(
                "https://www.reddit.com/search.json",
                params={"q": address, "sort": "relevance", "limit": 10},
                timeout=self.cfg.TIMEOUT,
            )
            data = resp.json()
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                results.append({
                    "title":     p.get("title", ""),
                    "subreddit": p.get("subreddit", ""),
                    "url":       "https://reddit.com" + p.get("permalink", ""),
                    "author":    p.get("author", ""),
                    "score":     p.get("score", 0),
                    "text":      p.get("selftext", "")[:800],
                })
        except Exception as e:
            results.append({"error": str(e)})
        return results

    # ── Source: GitHub ───────────────────────────────────────────────

    def _search_github(self, address: str) -> list:
        """
        GitHub public code search API.
        Add GITHUB_TOKEN in .env to raise rate limit from
        10 req/min (unauth) to 30 req/min.
        """
        results = []
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.cfg.GITHUB_TOKEN:
            headers["Authorization"] = f"token {self.cfg.GITHUB_TOKEN}"
        try:
            resp = self.s.get(
                "https://api.github.com/search/code",
                params={"q": address},
                headers=headers,
                timeout=self.cfg.TIMEOUT,
            )
            if resp.status_code == 200:
                for item in resp.json().get("items", [])[:10]:
                    repo = item.get("repository", {})
                    results.append({
                        "repo":       repo.get("full_name", ""),
                        "file":       item.get("name", ""),
                        "path":       item.get("path", ""),
                        "url":        item.get("html_url", ""),
                        "repo_owner": repo.get("owner", {}).get("login", ""),
                        "repo_url":   repo.get("html_url", ""),
                    })
            elif resp.status_code == 403:
                results.append({"error": "GitHub rate limit — set GITHUB_TOKEN in .env"})
            elif resp.status_code == 422:
                results.append({"error": "Query too short for GitHub search"})
        except Exception as e:
            results.append({"error": str(e)})
        return results

    # ── Source: BitcoinTalk ───────────────────────────────────────────

    def _search_bitcointalk(self, address: str) -> list:
        """Scrape BitcoinTalk forum search results."""
        results = []
        try:
            resp = self.s.get(
                "https://bitcointalk.org/index.php",
                params={"action": "search2", "search": address, "advanced": "1"},
                timeout=20,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for td in soup.find_all("td", class_="windowbg")[:10]:
                link = td.find("a")
                if link and "bitcointalk.org" in link.get("href", ""):
                    results.append({
                        "title": link.get_text(strip=True),
                        "url":   link.get("href", ""),
                    })
        except Exception as e:
            results.append({"error": str(e)})
        return results

    # ── Source: On-chain public comments/tags ──────────────────────────

    def _search_onchain_comments(self, address: str, chain: str) -> list:
        """
        Best-effort scrape of public community comments/tags directly
        attached to the address on a block explorer (Etherscan's
        "Public Name Tag" + comments, WalletExplorer's service label
        for Bitcoin). These are often the single richest signal since
        they're tied to the address itself, not a fuzzy text match.

        Page structure on these sites can change at any time — this
        degrades gracefully to an empty list if parsing fails.
        """
        results = []
        try:
            if chain == "ethereum":
                r = self.s.get(f"https://etherscan.io/address/{address}", timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")

                tag_el = soup.find(attrs={"class": re.compile("u-label", re.I)})
                if tag_el:
                    txt = tag_el.get_text(strip=True)
                    if txt:
                        results.append({"source": "Etherscan Public Name Tag", "text": txt})

                for c in soup.find_all(attrs={"class": re.compile("comment|note", re.I)})[:10]:
                    txt = c.get_text(strip=True)
                    if txt and len(txt) > 5:
                        results.append({"source": "Etherscan Comment", "text": txt[:300]})

            elif chain == "bitcoin":
                r = self.s.get(f"https://www.walletexplorer.com/address/{address}", timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")
                label_el = soup.find("h1")
                if label_el:
                    txt = label_el.get_text(strip=True)
                    if txt and address[:10] not in txt:
                        results.append({"source": "WalletExplorer Label", "text": txt})
        except Exception as e:
            results.append({"error": str(e)})
        return results

    # ── Confidence scoring ──────────────────────────────────────────────

    def _confidence(self, address: str, text: str) -> str:
        """
        Rate how likely a search result genuinely contains the wallet
        address verbatim, vs. a loose/fuzzy search-engine match.
          high   — full address found verbatim
          medium — a truncated/displayed form found (e.g. "0x1234…abcd")
          low    — address not actually present in the matched text
        """
        if not text:
            return "low"
        if address in text or address.lower() in text.lower():
            return "high"
        head, tail = address[:10], address[-6:]
        if head in text and tail in text:
            return "medium"
        return "low"

    # ── Entity extraction ────────────────────────────────────────────────

    def _extract_entities(self, text: str) -> dict:
        """
        Extract potential personal identifiers from aggregated public
        text. These identifiers were publicly posted by their owners
        alongside the wallet address.
        """
        emails = list(set(self._re_email.findall(text)))

        raw_phones = self._re_phone.findall(text)
        phones = list({
            p.strip() for p in raw_phones
            if len(re.sub(r"\D", "", p)) >= 10
        })

        usernames = list(set(self._re_username.findall(text)))
        telegrams = list(set(self._re_telegram.findall(text)))

        return {
            "emails":    emails[:20],
            "phones":    phones[:10],
            "usernames": usernames[:20],
            "telegrams": telegrams[:10],
        }
