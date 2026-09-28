"""UTC candle selection and Decimal return calculations."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from .models import ListingAnalysis, PriceObservation

OFFSETS=(0,7,30,90,180)

def analyze_listing(listing, contract, candles, as_of: date, mapping_status="AVAILABLE"):
    d0=listing.trading_started_at.astimezone(timezone.utc).date()
    if not contract:
        obs={n: PriceObservation(n,str(d0+timedelta(days=n)),None,None,mapping_status) for n in OFFSETS}
        return ListingAnalysis(listing,None,obs,{n:None for n in OFFSETS},mapping_status)
    d0_end=datetime.combine(d0+timedelta(days=1),time.min,tzinfo=timezone.utc)
    if contract.onboard_at >= d0_end:
        obs={n: PriceObservation(n,str(d0+timedelta(days=n)),None,None,"DELAYED_BINANCE_LISTING") for n in OFFSETS}
        return ListingAnalysis(listing,contract,obs,{n:None for n in OFFSETS},"DELAYED_BINANCE_LISTING")
    by_date={datetime.fromtimestamp(int(k[0])/1000,timezone.utc).date():k for k in candles}
    observations={}
    as_of_end=datetime.combine(as_of+timedelta(days=1),time.min,tzinfo=timezone.utc)
    for n in OFFSETS:
        target=d0+timedelta(days=n); candle=by_date.get(target)
        if target > as_of or datetime.combine(target+timedelta(days=1),time.min,tzinfo=timezone.utc)>as_of_end:
            status="NOT_MATURED"; price=close=None
        elif candle:
            close=datetime.fromtimestamp(int(candle[6])/1000,timezone.utc)
            if close >= as_of_end: status="NOT_MATURED"; price=None
            else: price=Decimal(str(candle[4])); status="AVAILABLE" if price>0 else ("NO_D0_CLOSE" if n==0 else "MISSING_TARGET_CANDLE")
        else:
            close=price=None
            status=("NO_D0_CLOSE" if n==0 else ("CONTRACT_DELISTED" if contract.status not in {"TRADING","PENDING_TRADING"} else "MISSING_TARGET_CANDLE"))
        observations[n]=PriceObservation(n,str(target),close,price,status)
    d0price=observations[0].close_price if observations[0].status=="AVAILABLE" else None
    returns={n: ((o.close_price/d0price)-Decimal(1))*Decimal(100) if n and d0price and o.status=="AVAILABLE" else None for n,o in observations.items()}
    return ListingAnalysis(listing,contract,observations,returns,observations[0].status)

def analyze_all(listings, contracts, client, as_of, mapper):
    results=[]
    for listing in listings:
        contract,status=mapper(listing.ticker,contracts)
        candles=[]
        if contract:
            start=int(datetime.combine(listing.trading_started_at.date(),time.min,tzinfo=timezone.utc).timestamp()*1000)
            try: candles=client.klines(contract.symbol,start,int(datetime.combine(as_of+timedelta(days=1),time.min,tzinfo=timezone.utc).timestamp()*1000)-1)
            except RuntimeError as exc:
                obs={n:PriceObservation(n,str(listing.trading_started_at.date()+timedelta(days=n)),None,None,"FETCH_ERROR",str(exc)) for n in OFFSETS}
                results.append(ListingAnalysis(listing,contract,obs,{n:None for n in OFFSETS},"FETCH_ERROR",str(exc))); continue
        results.append(analyze_listing(listing,contract,candles,as_of,status))
    return results

