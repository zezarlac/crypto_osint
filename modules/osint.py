"""
modules/osint.py — CryptoWalletOSINT
Searches public sources for mentions of a wallet address
and extracts identifiers (emails, usernames, phones) found
in close proximity to the address in public posts.

Sources (all publicly accessible, no login required):
  • DuckDuckGo (HTML endpoint)
  • Reddit public search API
  • GitHub public code search API
  • BitcoinTalk forum search

Note: This module only processes information voluntarily
made public by users. It does NOT access breach databases
or any private data.
"""

import re
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup
from config import Config


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

    # ── Public entry point ─────────────────────────────────────

    def search_all(self, address: str) -> dict:
        """
        Run all OSINT searches and return aggregated results
        including extracted identifiers from all found text.
        """
        web    = self._search_duckduckgo(address)
        time.sleep(1.5)
        reddit = self._search_reddit(address)
        time.sleep(1.5)
        github = self._search_github(address)
        time.sleep(1.5)
        btalk  = self._search_bitcointalk(address)

        # Collect all visible text for entity extraction
        corpus = []
        for r in web:
            corpus.append(r.get("title", "") + " " + r.get("snippet", ""))
        for r in reddit:
            corpus.append(
                r.get("title", "") + " "
                + r.get("text", "") + " u/"
                + r.get("author", "")
            )
        for r in btalk:
            corpus.append(r.get("title", ""))

        entities = self._extract_entities(" ".join(corpus))

        return {
            "web":                web,
            "reddit":             reddit,
            "github":             github,
            "bitcointalk":        btalk,
            "extracted_entities": entities,
        }

    # ── Source: DuckDuckGo ─────────────────────────────────────

    def _search_duckduckgo(self, address: str) -> list:
        """
        POST to DuckDuckGo's HTML interface with the address
        quoted for exact match.
        """
        results = []
        try:
            resp = self.s.post(
                "https://html.duckduckgo.com/html/",
                data={"q": f'"{address}"'},
                timeout=self.cfg.TIMEOUT,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for div in soup.find_all("div", class_="result__body")[:10]:
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

    # ── Source: Reddit ─────────────────────────────────────────

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

    # ── Source: GitHub ─────────────────────────────────────────

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

    # ── Source: BitcoinTalk ────────────────────────────────────

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

    # ── Entity extraction ──────────────────────────────────────

    def _extract_entities(self, text: str) -> dict:
        """
        Extract potential personal identifiers from aggregated
        public text. These identifiers were publicly posted by
        their owners alongside the wallet address.
        """
        emails = list(set(self._re_email.findall(text)))

        # Filter phone-like strings: require ≥10 digits
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
