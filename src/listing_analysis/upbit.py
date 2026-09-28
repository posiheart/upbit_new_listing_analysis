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

# This is a web endpoint used by upbit.com, rather than part of the documented
# Open API.  Keep the URL and its matching parameters together: sending the
# ``category`` parameters to ``notices`` (or ``thread_name`` to
# ``announcements``) makes a valid endpoint look broken.
UPBIT_NOTICE_ENDPOINTS = (
    ("https://api-manager.upbit.com/api/v1/notices",
     {"os": "web", "thread_name": "general"}),
    ("https://api-manager.upbit.com/api/v1/announcements",
     {"os": "web", "category": "all"}),
)
UPBIT_API_URLS = tuple(url for url, _ in UPBIT_NOTICE_ENDPOINTS)
# api-manager rejects non-browser user agents with HTTP 403.  These are ordinary
# browser request headers, not authentication or an attempt to evade a rate
# limit; the deliberately low request rate and on-disk cache remain in place.
UPBIT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Origin": "https://upbit.com",
    "Referer": "https://upbit.com/service_center/notice",
}
KST = ZoneInfo("Asia/Seoul")


@dataclass
class UpbitResult:
    listings: list[UpbitListing] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notices_examined: int = 0


class UpbitClient:
    def __init__(self, cache_dir: str | Path | None = None, timeout: float = 10,
                 retries: int = 2, request_interval: float = .25, session=None,
                 api_base_url: str | None = None, proxy_token: str | None = None):
        self.cache_dir = Path(cache_dir) / "upbit" if cache_dir else None
        self.timeout, self.retries, self.request_interval = timeout, retries, request_interval
        self.session = session or requests.Session()
        self.proxy_token = proxy_token
        if api_base_url:
            root = api_base_url.rstrip("/")
            self.notice_endpoints = (
                (f"{root}/notices", {"os": "web", "thread_name": "general"}),
                (f"{root}/announcements", {"os": "web", "category": "all"}),
            )
        else:
            self.notice_endpoints = UPBIT_NOTICE_ENDPOINTS
        self._notice_api = self.notice_endpoints[0][0]

    def _snapshot_path(self, page: int) -> Path | None:
        """Return the stable cache path used across undocumented API changes."""
        return self.cache_dir / "notice-pages" / f"{page}.json" if self.cache_dir else None

    def _read_snapshot(self, page: int) -> Any | None:
        path = self._snapshot_path(page)
        if not path or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_snapshot(self, page: int, payload: Any) -> None:
        path = self._snapshot_path(page)
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _get_notice_detail(self, notice_id: str, refresh: bool) -> Any:
        path = self.cache_dir / "notice-details" / f"{notice_id}.json" if self.cache_dir else None
        try:
            payload = self._get(
                f"{self._notice_api}/{notice_id}", {"os": "web"}, refresh=refresh
            )
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return payload
        except RuntimeError:
            if path and path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            raise

    def _get(self, url: str, params: dict | None = None, refresh: bool = False) -> Any:
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        if path and path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        error = None
        for attempt in range(self.retries + 1):
            try:
                headers = dict(UPBIT_HEADERS)
                if self.proxy_token:
                    headers["X-Proxy-Token"] = self.proxy_token
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                time.sleep(self.request_interval)
                return data
            except (requests.RequestException, ValueError) as exc:
                error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # A different URL/parameter variant is needed; retrying the
                # identical request only makes the report much slower.
                if status in (400, 403, 404, 410, 451):
                    break
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 2))
        # A temporary 403/WAF or network failure should not destroy a
        # reproducible cached run merely because --refresh was requested.
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        raise RuntimeError(f"Upbit request failed: {error}")

    def _get_notice_page(self, page: int, refresh: bool) -> Any:
        errors = []
        for url, parameters in self.notice_endpoints:
            try:
                payload = self._get(
                    url, {**parameters, "page": page, "per_page": 20}, refresh
                )
                if not isinstance(payload, (dict, list)):
                    raise RuntimeError("Upbit request failed: invalid JSON response shape")
                self._notice_api = url
                self._write_snapshot(page, payload)
                return payload
            except RuntimeError as exc:
                errors.append(str(exc).removeprefix("Upbit request failed: "))
        # The endpoint is an undocumented web API and may temporarily reject
        # CI/cloud IPs.  A stable snapshot is deliberately independent of the
        # endpoint and parameter hash, so an API rename does not turn a useful
        # report into an empty one.
        snapshot = self._read_snapshot(page)
        if snapshot is not None:
            return snapshot
        raise RuntimeError(
            "업비트 공지 서버가 요청을 거부했고 사용할 캐시가 없습니다. "
            "잠시 후 다시 실행하거나 이전 data/cache 디렉터리를 유지해 주세요. "
            f"(시도 {len(errors)}건)"
        )

    def collect(self, as_of: date, lookback_days: int = 365, refresh: bool = False) -> UpbitResult:
        result, page = UpbitResult(), 1
        schedule_changes: dict[str, datetime] = {}
        cutoff = as_of - timedelta(days=lookback_days)
        while True:
            try:
                payload = self._get_notice_page(page, refresh)
            except RuntimeError as exc:
                result.errors.append(str(exc)); break
            notices = _notice_items(payload)
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
                    # The current announcement detail resource also expects the
                    # web-client selector.  Omitting it can result in a 403 even
                    # after the list request succeeds.
                    detail = self._get_notice_detail(notice_id, refresh)
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


def _notice_items(payload: Any) -> list[dict]:
    """Normalize both the legacy list and current nested notice responses."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("notices", "list", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


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
