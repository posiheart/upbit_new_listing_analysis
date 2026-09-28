import json
from datetime import datetime, timezone
from pathlib import Path
from listing_analysis.upbit import UPBIT_HEADERS, UpbitClient, _notice_items, parse_notice

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

def test_collection_uses_notice_endpoint_with_its_required_parameters():
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
    assert session.calls[0][0].endswith("/api/v1/notices")
    assert session.calls[0][1]=={"os":"web","thread_name":"general","page":1,"per_page":20}
    assert UPBIT_HEADERS["Origin"]=="https://upbit.com"
    assert "Mozilla/5.0" in UPBIT_HEADERS["User-Agent"]

def test_collection_supplies_web_selector_to_notice_detail():
    class Session:
        def __init__(self): self.calls=[]
        def get(self,url,**kwargs):
            self.calls.append((url,kwargs.get("params")))
            class Response:
                def raise_for_status(self): pass
                def json(inner_self):
                    if url.endswith("/321"):
                        return {"data":{"id":321,"created_at":"2025-01-01T00:00:00Z",
                            "title":"거래지원 추가","content":"KRW-X 거래지원 시작 2025-01-02 10:00"}}
                    if len(self.calls)==1:
                        return {"data":[{"id":321,"created_at":"2025-01-01T00:00:00Z"}]}
                    return {"data":[]}
            return Response()
    session=Session()
    result=UpbitClient(session=session,request_interval=0).collect(
        datetime(2025,1,3,tzinfo=timezone.utc).date(),lookback_days=10)
    assert [row.ticker for row in result.listings]==["X"]
    assert session.calls[1][1]=={"os":"web"}

def test_collection_falls_back_to_announcements_and_remembers_detail_url():
    class Session:
        def __init__(self): self.urls=[]
        def get(self,url,**kwargs):
            self.urls.append(url)
            class Response:
                status_code=404 if "notices" in url else 200
                def raise_for_status(self):
                    if self.status_code == 404:
                        import requests
                        error=requests.HTTPError("404 Client Error"); error.response=self
                        raise error
                def json(self): return {"data":[]}
            return Response()
    session=Session()
    UpbitClient(session=session,retries=2,request_interval=0).collect(
        datetime(2025,1,1,tzinfo=timezone.utc).date())
    assert session.urls.count("https://api-manager.upbit.com/api/v1/notices")==1
    assert session.urls[-1].endswith("/api/v1/announcements")

def test_collection_reuses_stable_snapshot_when_all_variants_are_forbidden(tmp_path):
    snapshot=tmp_path/"upbit"/"notice-pages"/"1.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps({"data":[]}),encoding="utf-8")
    class Session:
        def get(self,url,**kwargs):
            import requests
            response=requests.Response(); response.status_code=403; response.url=url
            return response
    result=UpbitClient(cache_dir=tmp_path,session=Session(),retries=0,
        request_interval=0).collect(datetime(2025,1,1,tzinfo=timezone.utc).date())
    assert result.errors==[]

def test_collection_reports_concise_error_without_leaking_every_failed_url():
    class Session:
        def get(self,url,**kwargs):
            import requests
            response=requests.Response(); response.status_code=403; response.url=url
            return response
    result=UpbitClient(session=Session(),retries=0,request_interval=0).collect(
        datetime(2025,1,1,tzinfo=timezone.utc).date())
    assert len(result.errors)==1
    assert "사용할 캐시가 없습니다" in result.errors[0]
    assert "https://" not in result.errors[0]

def test_current_nested_notice_response_is_normalized():
    notices=[{"id":123}]
    assert _notice_items({"success":True,"data":{"notices":notices}})==notices
    assert _notice_items({"data":notices})==notices

def test_custom_api_base_and_proxy_token_are_used():
    class Session:
        def __init__(self): self.call=None
        def get(self,url,**kwargs):
            self.call=(url,kwargs)
            class Response:
                def raise_for_status(self): pass
                def json(self): return {"data":[]}
            return Response()
    session=Session()
    UpbitClient(session=session,request_interval=0,
        api_base_url="https://proxy.example/upbit/api/v1/",
        proxy_token="secret").collect(datetime(2025,1,1,tzinfo=timezone.utc).date())
    assert session.call[0]=="https://proxy.example/upbit/api/v1/notices"
    assert session.call[1]["headers"]["X-Proxy-Token"]=="secret"
