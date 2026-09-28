"""Small Binance USD-M Futures REST client and safe symbol mapper."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import requests
from .models import BinanceContract

# Binance documents these numbered USD-M REST hosts as alternatives to the
# primary host.  In particular, a CDN can return HTTP 451 for one hostname
# based on the runner's egress route while another official host is usable.
BASE_URLS = ("https://fapi.binance.com",) + tuple(
    f"https://fapi{i}.binance.com" for i in range(1, 5)
)
BINANCE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

class BinanceClient:
    def __init__(self, timeout=10, retries=2, session=None, base_urls=None, cache_dir=None):
        self.timeout, self.retries = timeout, retries
        self.session = session or requests.Session()
        self.base_urls = tuple(base_urls or BASE_URLS)
        self.cache_dir = Path(cache_dir) / "binance" if cache_dir else None
    def _get(self, path, params=None):
        key=json.dumps({"path":path,"params":params or {}},sort_keys=True,separators=(",",":"))
        cache_path=(self.cache_dir / (hashlib.sha256(key.encode()).hexdigest()+".json")) if self.cache_dir else None
        if cache_path and cache_path.exists():
            try: return json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError,ValueError): pass
        errors = []
        for base_url in self.base_urls:
            for _ in range(self.retries + 1):
                try:
                    r=self.session.get(base_url+path, params=params, timeout=self.timeout,
                        headers=BINANCE_HEADERS)
                    r.raise_for_status()
                    data=r.json()
                    if not isinstance(data,(dict,list)):
                        raise ValueError("response was not a JSON object or array")
                    if isinstance(data,dict) and "code" in data and "msg" in data:
                        raise ValueError(f"API error {data['code']}: {data['msg']}")
                    if cache_path:
                        cache_path.parent.mkdir(parents=True,exist_ok=True)
                        cache_path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
                    return data
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{base_url}: {exc}")
                    # Host-specific access failures will not improve on retry.
                    status=getattr(getattr(exc,"response",None),"status_code",None)
                    # HTML in a 200 response is normally a host-level WAF or
                    # geo-block too, so do not repeat an identical bad request.
                    if status in (400,403,404,410,418,429,451) or isinstance(exc,ValueError): break
        raise RuntimeError(
            "Binance USD-M API 접속이 모든 공식 호스트에서 거부되었습니다. "
            "API 주소 오류가 아니라 실행 위치의 지역/IP 제한일 수 있습니다. "
            "접속 가능한 네트워크에서 다시 실행하거나 data/cache 디렉터리를 유지해 주세요. "
            f"(호스트 {len(self.base_urls)}개)"
        )
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
