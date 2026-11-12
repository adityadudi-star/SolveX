"""Official SEC EDGAR client: truthful User-Agent, rate limiting, exponential backoff, timeouts, disk cache.

Never fabricates data: any failure raises SecError so the workflow surfaces a visible error.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from app.config import Settings, get_settings

# Per-workflow counters (set by the workflow runner; read for observability).
current_stats: contextvars.ContextVar[dict | None] = contextvars.ContextVar("sec_stats", default=None)


class SecError(RuntimeError):
    def __init__(self, message: str, kind: str = "sec_error", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass
class FilingRef:
    accession: str
    form: str
    filing_date: date | None
    report_date: date | None
    primary_document: str
    cik: str

    @property
    def fiscal_year(self) -> int | None:
        return self.report_date.year if self.report_date else (self.filing_date.year if self.filing_date else None)

    @property
    def url(self) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/{self.accession.replace('-', '')}/{self.primary_document}"


def pad_cik(cik: str | int) -> str:
    return str(int(cik)).zfill(10)


def _d(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


class _RateLimiter:
    def __init__(self, per_sec: float):
        self.interval = 1.0 / max(per_sec, 0.1)
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


class SecClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.s = settings or get_settings()
        self._limiter = _RateLimiter(self.s.sec_rate_limit_per_sec)
        self._transport = transport
        self._sleep = sleep
        self.cache_dir = Path(self.s.cache_dir)
        self.last_ok: datetime | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ plumbing
    def _bump(self, key: str, n: int = 1) -> None:
        st = current_stats.get()
        if st is not None:
            st[key] = st.get(key, 0) + n

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".bin")

    def _read_cache(self, url: str, ttl: int) -> bytes | None:
        p = self._cache_path(url)
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl:
            return p.read_bytes()
        return None

    def _write_cache(self, url: str, content: bytes) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path(url).with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(self._cache_path(url))

    def _get(self, url: str, ttl: int | None = None) -> bytes:
        if not self.s.sec_configured:
            raise SecError(
                "SEC access is not configured. Set SEC_CONTACT_EMAIL in backend/.env to a real contact "
                "email (required by the SEC fair-access policy).", kind="not_configured")
        ttl = self.s.sec_cache_ttl_seconds if ttl is None else ttl
        cached = self._read_cache(url, ttl)
        if cached is not None:
            self._bump("sec_cache_hits")
            return cached
        headers = {"User-Agent": self.s.sec_user_agent, "Accept-Encoding": "gzip, deflate"}
        last: Exception | None = None
        for attempt in range(self.s.sec_max_retries + 1):
            self._limiter.wait()
            self._bump("sec_requests")
            try:
                with httpx.Client(timeout=self.s.sec_timeout_seconds, transport=self._transport,
                                  follow_redirects=True, headers=headers) as c:
                    r = c.get(url)
                if r.status_code == 200:
                    self._write_cache(url, r.content)
                    self.last_ok, self.last_error = datetime.utcnow(), None
                    return r.content
                if r.status_code in (403,):
                    raise SecError(f"SEC refused the request (403) for {url}. Check SEC_CONTACT_EMAIL / User-Agent and rate limits.",
                                   kind="forbidden", status=403)
                if r.status_code == 404:
                    raise SecError(f"SEC resource not found (404): {url}", kind="not_found", status=404)
                if r.status_code in (429, 500, 502, 503, 504):
                    last = SecError(f"SEC temporary error {r.status_code}", kind="temporary", status=r.status_code)
                else:
                    raise SecError(f"Unexpected SEC response {r.status_code} for {url}", kind="http_error", status=r.status_code)
            except SecError as e:
                if e.kind != "temporary":
                    self.last_error = str(e)
                    raise
                last = e
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = SecError(f"SEC network error: {type(e).__name__}: {e}", kind="network")
            if attempt < self.s.sec_max_retries:
                self._bump("sec_retries")
                self._sleep(min(30.0, (2 ** attempt) + random.random()))
        self.last_error = str(last)
        raise SecError(f"SEC request failed after {self.s.sec_max_retries + 1} attempts: {last}",
                       kind=getattr(last, "kind", "sec_error"))

    def _json(self, url: str, ttl: int | None = None) -> Any:
        try:
            return json.loads(self._get(url, ttl))
        except json.JSONDecodeError as e:
            raise SecError(f"SEC returned invalid JSON for {url}: {e}", kind="bad_payload") from e

    # ------------------------------------------------------------------ public API
    def search_companies(self, query: str, limit: int = 10) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        data = self._json(f"{self.s.sec_base_www}/files/company_tickers.json", ttl=7 * 24 * 3600)
        rows = data.values() if isinstance(data, dict) else data
        scored: list[tuple[int, dict]] = []
        for r in rows:
            name, tick = str(r.get("title", "")), str(r.get("ticker", ""))
            nl, tl = name.lower(), tick.lower()
            if tl == q:
                score = 0
            elif nl == q:
                score = 1
            elif nl.startswith(q) or tl.startswith(q):
                score = 2
            elif q in nl:
                score = 3
            else:
                continue
            scored.append((score, {"cik": pad_cik(r["cik_str"]), "name": name, "ticker": tick}))
        scored.sort(key=lambda t: (t[0], t[1]["name"]))
        return [x for _, x in scored[:limit]]

    def submissions(self, cik: str) -> dict:
        return self._json(f"{self.s.sec_base_data}/submissions/CIK{pad_cik(cik)}.json", ttl=6 * 3600)

    def list_10k_filings(self, cik: str, include_older: bool = False) -> tuple[dict, list[FilingRef]]:
        sub = self.submissions(cik)
        blocks = [sub.get("filings", {}).get("recent", {})]
        if include_older:
            for f in sub.get("filings", {}).get("files", []):
                try:
                    blocks.append(self._json(f"{self.s.sec_base_data}/submissions/{f['name']}", ttl=6 * 3600))
                except SecError:
                    continue
        out: dict[str, FilingRef] = {}
        for b in blocks:
            forms = b.get("form", [])
            for i, form in enumerate(forms):
                if form not in ("10-K", "10-K405", "10-KSB"):
                    continue
                acc = b["accession_number"][i] if "accession_number" in b else b["accessionNumber"][i]
                out[acc] = FilingRef(
                    accession=acc, form=form, filing_date=_d(b["filingDate"][i]), report_date=_d(b["reportDate"][i]),
                    primary_document=b["primaryDocument"][i], cik=pad_cik(cik),
                )
        refs = sorted(out.values(), key=lambda f: f.report_date or date.min, reverse=True)
        return sub, refs

    def company_facts(self, cik: str) -> dict:
        return self._json(f"{self.s.sec_base_data}/api/xbrl/companyfacts/CIK{pad_cik(cik)}.json", ttl=12 * 3600)

    def filing_html(self, ref: FilingRef) -> bytes:
        return self._get(ref.url, ttl=30 * 24 * 3600)

    def health(self, live: bool = False) -> dict:
        info: dict[str, Any] = {
            "configured": self.s.sec_configured,
            "user_agent": self.s.sec_user_agent if self.s.sec_configured else None,
            "status": "not_configured" if not self.s.sec_configured else "unknown",
            "last_ok": self.last_ok.isoformat() if self.last_ok else None,
            "last_error": self.last_error,
        }
        if live and self.s.sec_configured:
            t0 = time.monotonic()
            try:
                self._get(f"{self.s.sec_base_data}/submissions/CIK0000320193.json", ttl=0)
                info.update(status="ok", latency_ms=int((time.monotonic() - t0) * 1000))
            except SecError as e:
                info.update(status="error", last_error=str(e))
        elif self.last_ok and not self.last_error:
            info["status"] = "ok"
        elif self.last_error:
            info["status"] = "error"
        return info


_client: SecClient | None = None


def get_sec_client() -> SecClient:
    global _client
    if _client is None:
        _client = SecClient()
    return _client


def set_sec_client(c: SecClient | None) -> None:
    global _client
    _client = c
