from datetime import date,datetime,timezone
from decimal import Decimal
from listing_analysis.analysis import analyze_listing
from listing_analysis.models import BinanceContract,UpbitListing

def listing(hour=0): return UpbitListing("X","엑스","KRW","1","https://x",datetime(2025,1,1,tzinfo=timezone.utc),datetime(2025,1,1,hour,tzinfo=timezone.utc))
def contract(onboard=0,status="TRADING"): return BinanceContract("XUSDT","X","USDT","PERPETUAL",status,datetime.fromtimestamp(onboard,tz=timezone.utc),Decimal(1))
def candle(day,close):
    start=datetime(2025,1,day,tzinfo=timezone.utc); return [int(start.timestamp()*1000),"0","0","0",str(close),"0",int((start.timestamp()+86399)*1000)]

def test_exact_dates_decimal_return_and_missing():
    a=analyze_listing(listing(23),contract(),[candle(1,"2"),candle(8,"3")],date(2025,7,20))
    assert a.observations[7].target_date=="2025-01-08" and a.returns[7]==Decimal("50.0")
    assert a.observations[30].status=="MISSING_TARGET_CANDLE"
def test_not_matured_missing_contract_and_delayed():
    a=analyze_listing(listing(),contract(),[candle(1,"2")],date(2025,1,20)); assert a.observations[30].status=="NOT_MATURED"
    assert analyze_listing(listing(),None,[],date(2025,2,1),"NO_BINANCE_CONTRACT").observations[0].status=="NO_BINANCE_CONTRACT"
    late=contract(datetime(2025,1,2,tzinfo=timezone.utc).timestamp()); assert analyze_listing(listing(),late,[],date(2025,2,1)).mapping_status=="DELAYED_BINANCE_LISTING"
def test_zero_d0_and_delisted():
    a=analyze_listing(listing(),contract(status="SETTLING"),[candle(1,"0")],date(2025,7,20))
    assert a.observations[0].status=="NO_D0_CLOSE" and all(v is None for v in a.returns.values())
    assert a.observations[180].status=="CONTRACT_DELISTED"

