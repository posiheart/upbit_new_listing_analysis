"""Collection and conservative parsing of official Upbit notices."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .models import UpbitListing

UPBIT_API = "https://api-manager.upbit.com/api/v1/notices"
USER_AGENT = "upbit-listing-analysis/0.1 (+research; respectful cache)"
KST = ZoneInfo("Asia/Seoul")


@dataclass
class UpbitResult:
    listings: list[UpbitListing] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notices_examined: int = 0


class UpbitClient:
    def __init__(self, cache_dir: str | Path | None = None, timeout: float = 10,
                 retries: int = 2, request_interval: float = .25, session=None):
        self.cache_dir = Path(cache_dir) / "upbit" if cache_dir else None
        self.timeout, self.retries, self.request_interval = timeout, retries, request_interval
        self.session = session or requests.Session()

    def _get(self, url: str, params: dict | None = None, refresh: bool = False) -> Any:
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        if path and path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        error = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout,
                                            headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
                data = response.json()
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                time.sleep(self.request_interval)
                return data
            except (requests.RequestException, ValueError) as exc:
                error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 2))
        raise RuntimeError(f"Upbit request failed: {error}")

    def collect(self, as_of: date, lookback_days: int = 365, refresh: bool = False) -> UpbitResult:
        result, page = UpbitResult(), 1
        schedule_changes: dict[str, datetime] = {}
        cutoff = as_of - timedelta(days=lookback_days)
        while True:
            try:
                payload = self._get(UPBIT_API, {"page": page, "per_page": 20}, refresh)
            except RuntimeError as exc:
                result.errors.append(str(exc)); break
            notices = payload.get("data", payload if isinstance(payload, list) else [])
            if not notices: break
            stop = False
            for item in notices:
                published = parse_datetime(item.get("created_at") or item.get("createdAt"))
                if not published:
                    result.errors.append(f"notice {item.get('id')}: invalid publication date"); continue
                if published.date() < cutoff: stop = True; continue
                if published.date() > as_of: continue
                result.notices_examined += 1
                notice_id = str(item.get("id"))
                try:
                    detail = self._get(f"{UPBIT_API}/{notice_id}", refresh=refresh)
                    body = detail.get("data", detail)
                    for ticker, changed_at in parse_schedule_change(body, item).items():
                        schedule_changes.setdefault(ticker, changed_at)  # API pages are newest first
                    result.listings.extend(parse_notice(body, item))
                except Exception as exc:
                    result.errors.append(f"notice {notice_id}: {exc}")
            if stop: break
            page += 1
        # A later schedule-change notice supersedes the time in the original notice.
        result.listings = [UpbitListing(x.ticker, x.korean_name, x.market, x.notice_id,
            x.notice_url, x.notice_published_at, schedule_changes.get(x.ticker, x.trading_started_at))
            for x in result.listings]
        unique = {(x.ticker, x.market, x.trading_started_at): x for x in result.listings}
        result.listings = list(unique.values())
        return result


def parse_datetime(value: Any) -> datetime | None:
    if not value: return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (dt.replace(tzinfo=KST) if dt.tzinfo is None else dt).astimezone(timezone.utc)
    except ValueError: return None


def parse_notice(detail: dict, summary: dict | None = None) -> list[UpbitListing]:
    summary = summary or {}
    title = str(detail.get("title") or summary.get("title") or "")
    html = str(detail.get("content") or detail.get("body") or "")
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    whole = title + " " + text
    if "거래지원 추가" not in whole or not re.search(r"KRW\s*마켓|원화\s*마켓|KRW[-/ ]", whole, re.I):
        return []
    start = _parse_start(whole)
    if not start: raise ValueError("KRW trading start time was not parseable")
    # Prefer explicit market codes, then ticker/name rows such as "에이(A) | KRW".
    tickers = set(re.findall(r"\bKRW[-/ ]([A-Z0-9]{1,15})\b", whole, re.I))
    tickers.update(re.findall(r"\(([A-Z0-9]{1,15})\)\s*(?:\||/)?\s*KRW", whole, re.I))
    if not tickers:
        raise ValueError("KRW ticker was not parseable")
    names = {t: t for t in tickers}
    for name, ticker in re.findall(r"([가-힣][가-힣0-9 ]*?)\s*\(([A-Z0-9]{1,15})\)", whole):
        if ticker in names: names[ticker] = name.strip()
    nid = str(detail.get("id") or summary.get("id") or "")
    pub = parse_datetime(detail.get("created_at") or summary.get("created_at") or summary.get("createdAt"))
    if not pub: raise ValueError("publication date was not parseable")
    url = detail.get("url") or f"https://upbit.com/service_center/notice?id={nid}"
    return [UpbitListing(t.upper(), names[t], "KRW", nid, url, pub, start) for t in sorted(tickers)]


def parse_schedule_change(detail: dict, summary: dict | None = None) -> dict[str, datetime]:
    """Extract a ticker/time from a separate trading schedule correction notice."""
    summary = summary or {}
    whole = str(detail.get("title") or summary.get("title") or "") + " " + BeautifulSoup(
        str(detail.get("content") or detail.get("body") or ""), "html.parser").get_text(" ", strip=True)
    if "변경" not in whole or "거래지원" not in whole:
        return {}
    start = _parse_start(whole)
    if not start:
        return {}
    tickers = set(re.findall(r"\bKRW[-/ ]([A-Z0-9]{1,15})\b", whole, re.I))
    tickers.update(re.findall(r"\(([A-Z0-9]{1,15})\)", whole, re.I))
    return {ticker.upper(): start for ticker in tickers}


def _parse_start(text: str) -> datetime | None:
    candidates = re.findall(r"(?:변경|거래지원\s*개시|거래\s*지원\s*시작|거래지원\s*시작)[^\d]{0,40}(20\d{2})[.년/-]\s*(\d{1,2})[.월/-]\s*(\d{1,2})[^\d]{0,20}(\d{1,2}):(\d{2})", text)
    if not candidates:
        candidates = re.findall(r"(20\d{2})[.년/-]\s*(\d{1,2})[.월/-]\s*(\d{1,2})[^\d]{0,20}(\d{1,2}):(\d{2})", text)
    if not candidates: return None
    y, m, d, hh, mm = map(int, candidates[-1]) # latest correction in the notice wins
    return datetime(y, m, d, hh, mm, tzinfo=KST).astimezone(timezone.utc)
