import json
from datetime import datetime, timezone
from pathlib import Path
from listing_analysis.upbit import UpbitClient, _notice_items, parse_notice

def test_multi_asset_and_kst_conversion():
    data=json.loads(Path("tests/fixtures/upbit_multi.json").read_text())
    rows=parse_notice(data)
    assert [r.ticker for r in rows]==["A","B"]
    assert rows[0].trading_started_at==datetime(2025,1,2,5,0,tzinfo=timezone.utc)

def test_btc_usdt_only_excluded_and_krw_mixed_included():
    base={"id":1,"created_at":"2025-01-01T00:00:00Z","title":"거래지원 추가", "content":"BTC-X, USDT-X 거래지원 시작 2025-01-02 10:00"}
    assert parse_notice(base)==[]
    base["content"]="BTC-X, KRW-X 거래지원 시작 2025-01-02 10:00"
    assert [x.ticker for x in parse_notice(base)]==["X"]

def test_changed_start_uses_last_explicit_time():
    d={"id":2,"created_at":"2025-01-01T00:00:00Z","title":"X 거래지원 추가", "content":"KRW-X 거래지원 시작 2025-01-02 10:00 변경: 2025-01-02 12:30"}
    assert parse_notice(d)[0].trading_started_at.hour==3

def test_collection_supplies_required_web_notice_parameters():
    class Session:
        def __init__(self): self.calls=[]
        def get(self,url,**kwargs):
            self.calls.append((url,kwargs["params"]))
            class Response:
                def raise_for_status(self): pass
                def json(self): return {"data":[]}
            return Response()
    session=Session()
    UpbitClient(session=session,request_interval=0).collect(datetime(2025,1,1,tzinfo=timezone.utc).date())
    assert session.calls[0][1]=={"os":"web","category":"all","page":1,"per_page":20}

def test_current_nested_notice_response_is_normalized():
    notices=[{"id":123}]
    assert _notice_items({"success":True,"data":{"notices":notices}})==notices
    assert _notice_items({"data":notices})==notices
