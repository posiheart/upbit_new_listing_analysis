from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
from pathlib import Path
from .analysis import analyze_all
from .binance import BinanceClient,contracts_from_exchange_info,load_overrides,map_contract
from .models import json_value
from .report import render_report
from .upbit import UpbitClient

def write_text(path, content):
    """Write an output file, creating its destination directory when needed."""
    destination=Path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(content,encoding="utf-8")

def parser():
    p=argparse.ArgumentParser(); p.add_argument("--as-of",type=date.fromisoformat); p.add_argument("--lookback-days",type=int,default=365); p.add_argument("--output",default="output/report.html"); p.add_argument("--cache-dir",default="data/cache"); p.add_argument("--refresh",action="store_true"); p.add_argument("--request-timeout",type=float,default=10); p.add_argument("--symbol-overrides",default="config/symbol_overrides.json"); p.add_argument("--save-json")
    p.add_argument("--upbit-api-base-url",default=os.getenv("UPBIT_API_BASE_URL"))
    p.add_argument("--binance-api-base-urls",default=os.getenv("BINANCE_API_BASE_URLS"))
    p.add_argument("--proxy-token",default=os.getenv("API_PROXY_TOKEN"))
    p.add_argument("--fail-on-collection-error",action="store_true")
    return p
def main(argv=None):
    args=parser().parse_args(argv); as_of=args.as_of or datetime.now(timezone.utc).date()
    up=UpbitClient(args.cache_dir,args.request_timeout,api_base_url=args.upbit_api_base_url,
        proxy_token=args.proxy_token if args.upbit_api_base_url else None).collect(
            as_of,args.lookback_days,args.refresh)
    base_urls=tuple(x.strip().rstrip("/") for x in (args.binance_api_base_urls or "").split(",") if x.strip()) or None
    bc=BinanceClient(args.request_timeout,cache_dir=args.cache_dir,base_urls=base_urls,
        proxy_token=args.proxy_token if base_urls else None); warnings=list(up.errors)
    try: contracts=contracts_from_exchange_info(bc.exchange_info())
    except RuntimeError as exc: contracts=[]; warnings.append(str(exc))
    overrides=load_overrides(args.symbol_overrides)
    analyses=analyze_all(up.listings,contracts,bc,as_of,lambda t,cs:map_contract(t,cs,overrides))
    write_text(args.output,render_report(analyses,as_of,up.notices_examined,warnings))
    if args.save_json: write_text(args.save_json,json.dumps(json_value(analyses),ensure_ascii=False,indent=2))
    if args.fail_on_collection_error and warnings:
        raise SystemExit("collection failed; refusing to replace the last successful report: " + "; ".join(warnings))

if __name__=="__main__": main()
