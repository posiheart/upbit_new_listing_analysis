"""Small Binance USD-M Futures REST client and safe symbol mapper."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import requests
from .models import BinanceContract

# Binance documents these numbered USD-M REST hosts as alternatives to the
# primary host.  In particular, a CDN can return HTTP 451 for one hostname
# based on the runner's egress route while another official host is usable.
BASE_URLS = tuple(f"https://fapi{i}.binance.com" for i in range(1, 5)) + (
    "https://fapi.binance.com",
    # Binance's own website reverse-proxies the same public futures routes and
    # is useful when every fapi hostname is geo-blocked by an egress provider.
    "https://www.binance.com",
)

class BinanceClient:
    def __init__(self, timeout=10, retries=2, session=None, base_urls=None):
        self.timeout, self.retries = timeout, retries
        self.session = session or requests.Session()
        self.base_urls = tuple(base_urls or BASE_URLS)
    def _get(self, path, params=None):
        errors = []
        for base_url in self.base_urls:
            for _ in range(self.retries + 1):
                try:
                    r=self.session.get(base_url+path, params=params, timeout=self.timeout,
                        headers={"User-Agent":"Mozilla/5.0 (compatible; upbit-listing-analysis/0.1)",
                                 "Accept":"application/json"})
                    r.raise_for_status()
                    data=r.json()
                    if not isinstance(data,(dict,list)):
                        raise ValueError("response was not a JSON object or array")
                    return data
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{base_url}: {exc}")
                    # Host-specific access failures will not improve on retry.
                    status=getattr(getattr(exc,"response",None),"status_code",None)
                    # HTML in a 200 response is normally a host-level WAF or
                    # geo-block too, so do not repeat an identical bad request.
                    if status in (400,403,404,410,418,429,451) or isinstance(exc,ValueError): break
        raise RuntimeError("Binance request failed on all official hosts: " + "; ".join(dict.fromkeys(errors)))
    def exchange_info(self): return self._get("/fapi/v1/exchangeInfo")
    def klines(self, symbol, start_ms, end_ms):
        return self._get("/fapi/v1/klines", {"symbol":symbol,"interval":"1d","startTime":start_ms,"endTime":end_ms,"limit":1000})

def contracts_from_exchange_info(data):
    out=[]
    for x in data.get("symbols", []):
        if x.get("quoteAsset") != "USDT" or x.get("contractType") != "PERPETUAL": continue
        symbol=x["symbol"]; base=x.get("baseAsset", "")
        multiplier=Decimal("1")
        match=re.match(r"^(\d+)(.+)$", base)
        if match: multiplier=Decimal(match.group(1))
        onboard=datetime.fromtimestamp(int(x["onboardDate"])/1000, timezone.utc)
        out.append(BinanceContract(symbol,base,"USDT","PERPETUAL",x.get("status",""),onboard,multiplier))
    return out

def load_overrides(path):
    if not path or not Path(path).exists(): return {}
    raw=json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(x["upbit_ticker"]).upper(): x for x in (raw if isinstance(raw,list) else raw.get("overrides",[]))}

def map_contract(ticker, contracts, overrides=None):
    overrides=overrides or {}; override=overrides.get(ticker.upper())
    if override:
        if not override.get("binance_symbol"): return None, "NO_BINANCE_CONTRACT"
        matches=[c for c in contracts if c.symbol==override["binance_symbol"]]
        if len(matches)==1:
            c=matches[0]
            mult=Decimal(str(override.get("contract_multiplier",c.contract_multiplier)))
            return BinanceContract(c.symbol,c.base_asset,c.quote_asset,c.contract_type,c.status,c.onboard_at,mult),"AVAILABLE"
        return None,"SYMBOL_MAPPING_REQUIRED"
    exact=[c for c in contracts if c.base_asset==ticker and c.symbol==ticker+"USDT"]
    scaled=[c for c in contracts if re.fullmatch(r"\d+"+re.escape(ticker),c.base_asset)]
    candidates=exact+scaled
    return (candidates[0],"AVAILABLE") if len(candidates)==1 else (None,"NO_BINANCE_CONTRACT" if not candidates else "SYMBOL_MAPPING_REQUIRED")
