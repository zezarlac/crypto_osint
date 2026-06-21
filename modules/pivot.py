"""
modules/pivot.py — CryptoWalletOSINT
Identity pivot: once an OSINT search surfaces a username or email
near a wallet address, this checks whether that same identifier
exists on other platforms — turning one data point into a small
cross-platform footprint.

Only free, public, unauthenticated endpoints are used:
  • GitHub   — profile lookup + commit-author search
  • Keybase  — profile + verified social proofs (often links
               Twitter/GitHub/Reddit/etc. in a single response)
  • Telegram — public username resolution (t.me/<user>)
  • Gravatar — public profile tied to an email's hash
"""

import hashlib
import time
import requests
from config import Config

MAX_USERNAMES_TO_CHECK = 5
MAX_EMAILS_TO_CHECK    = 3


class IdentityPivot:
    def __init__(self):
        self.cfg = Config()
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (CryptoWalletOSINT/1.0 Educational Research)"
        })

    # ── Public entry point ──────────────────────────────────────

    def pivot_all(self, entities: dict) -> dict:
        """Run cross-platform checks on extracted usernames/emails."""
        usernames = entities.get("usernames", [])[:MAX_USERNAMES_TO_CHECK]
        emails    = entities.get("emails", [])[:MAX_EMAILS_TO_CHECK]

        results = {"usernames": {}, "emails": {}}
        for u in usernames:
            results["usernames"][u] = self.check_username(u)
            time.sleep(self.cfg.RATE_DELAY)
        for e in emails:
            results["emails"][e] = self.check_email(e)
            time.sleep(self.cfg.RATE_DELAY)
        return results

    # ── Username checks ───────────────────────────────────────────

    def check_username(self, username: str) -> dict:
        return {
            "github":   self._check_github_user(username),
            "keybase":  self._check_keybase(username),
            "telegram": self._check_telegram_user(username),
        }

    def _github_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.cfg.GITHUB_TOKEN:
            headers["Authorization"] = f"token {self.cfg.GITHUB_TOKEN}"
        return headers

    def _check_github_user(self, username: str) -> dict:
        try:
            r = self.s.get(f"https://api.github.com/users/{username}",
                            headers=self._github_headers(), timeout=10)
            if r.status_code == 200:
                d = r.json()
                return {
                    "exists": True, "url": d.get("html_url", ""),
                    "name": d.get("name", "") or "", "bio": d.get("bio", "") or "",
                    "public_repos": d.get("public_repos", 0),
                    "created_at": d.get("created_at", ""),
                }
            return {"exists": False}
        except Exception as e:
            return {"exists": None, "error": str(e)}

    def _check_keybase(self, username: str) -> dict:
        try:
            r = self.s.get(
                "https://keybase.io/_/api/1.0/user/lookup.json",
                params={"username": username}, timeout=10
            ).json()
            users = r.get("them", [])
            if users and users[0]:
                u = users[0]
                profile = u.get("profile", {}) or {}
                proofs = [
                    p.get("proof_type", "")
                    for p in (u.get("proofs_summary", {}) or {}).get("all", [])
                ]
                return {
                    "exists": True,
                    "full_name": profile.get("full_name", ""),
                    "linked_proofs": proofs,   # e.g. ["twitter", "github", "reddit"]
                }
            return {"exists": False}
        except Exception as e:
            return {"exists": None, "error": str(e)}

    def _check_telegram_user(self, username: str) -> dict:
        """
        Best-effort check via t.me/<username>'s public preview page.
        Telegram doesn't offer a free official lookup API.
        """
        try:
            r = self.s.get(f"https://t.me/{username}", timeout=10)
            text = r.text
            exists = "tgme_page_title" in text and "If you have Telegram" not in text[:300]
            return {"exists": bool(exists), "url": f"https://t.me/{username}"}
        except Exception as e:
            return {"exists": None, "error": str(e)}

    # ── Email checks ───────────────────────────────────────────────

    def check_email(self, email: str) -> dict:
        return {
            "gravatar":       self._check_gravatar(email),
            "github_commits": self._check_github_commits(email),
        }

    def _check_gravatar(self, email: str) -> dict:
        try:
            h = hashlib.md5(email.strip().lower().encode()).hexdigest()
            r = self.s.get(f"https://www.gravatar.com/{h}.json", timeout=10)
            if r.status_code == 200:
                d = r.json().get("entry", [{}])[0]
                return {
                    "exists": True,
                    "display_name": d.get("displayName", ""),
                    "profile_url":  d.get("profileUrl", ""),
                }
            return {"exists": False}
        except Exception as e:
            return {"exists": None, "error": str(e)}

    def _check_github_commits(self, email: str) -> dict:
        """Find GitHub commits authored with this email — often reveals a real username."""
        try:
            r = self.s.get(
                "https://api.github.com/search/commits",
                params={"q": f"author-email:{email}"},
                headers=self._github_headers(), timeout=10,
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                if items:
                    author = items[0].get("author", {}) or {}
                    return {
                        "exists": True,
                        "commits_found":   len(items),
                        "github_username": author.get("login", ""),
                        "sample_repo":     items[0].get("repository", {}).get("full_name", ""),
                    }
            return {"exists": False}
        except Exception as e:
            return {"exists": None, "error": str(e)}
