import requests
from listing_analysis.binance import BASE_URLS,BINANCE_HEADERS,BinanceClient,contracts_from_exchange_info,map_contract

def contracts():
    return contracts_from_exchange_info({"symbols":[
      {"symbol":"ABCUSDT","baseAsset":"ABC","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING","onboardDate":1},
      {"symbol":"1000PEPEUSDT","baseAsset":"1000PEPE","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING","onboardDate":1},
      {"symbol":"ABCUSDC","baseAsset":"ABC","quoteAsset":"USDC","contractType":"PERPETUAL","status":"TRADING","onboardDate":1}]})
def test_exact_and_multiplier_mapping():
    assert map_contract("ABC",contracts())[0].symbol=="ABCUSDT"
    c,status=map_contract("PEPE",contracts()); assert (c.symbol,str(c.contract_multiplier),status)==("1000PEPEUSDT","1000","AVAILABLE")
def test_missing_and_override_exclusion():
    assert map_contract("NONE",contracts())[1]=="NO_BINANCE_CONTRACT"
    assert map_contract("ABC",contracts(),{"ABC":{"binance_symbol":None}})[1]=="NO_BINANCE_CONTRACT"

def test_access_denied_host_falls_back_without_retrying_it():
    class Session:
        def __init__(self): self.urls=[]
        def get(self,url,**kwargs):
            self.urls.append(url)
            class Response:
                status_code=451 if "blocked" in url else 200
                def raise_for_status(self):
                    if self.status_code != 200:
                        error=requests.HTTPError("451 Client Error")
                        error.response=self
                        raise error
                def json(self): return {"symbols":[]}
            return Response()
    session=Session()
    result=BinanceClient(retries=2,session=session,base_urls=("https://blocked","https://ok")).exchange_info()
    assert result=={"symbols":[]}
    assert session.urls==["https://blocked/fapi/v1/exchangeInfo","https://ok/fapi/v1/exchangeInfo"]

def test_non_json_waf_response_falls_back_without_retries():
    class Session:
        def __init__(self): self.urls=[]
        def get(self,url,**kwargs):
            self.urls.append(url)
            class Response:
                def raise_for_status(self): pass
                def json(self):
                    if "waf" in url: raise requests.JSONDecodeError("bad JSON","<html>",0)
                    return {"symbols":[]}
            return Response()
    session=Session()
    assert BinanceClient(retries=2,session=session,base_urls=("https://waf","https://ok")).exchange_info()=={"symbols":[]}
    assert session.urls==["https://waf/fapi/v1/exchangeInfo","https://ok/fapi/v1/exchangeInfo"]

def test_official_primary_host_and_browser_headers_are_used():
    assert BASE_URLS[0]=="https://fapi.binance.com"
    assert "www.binance.com" not in BASE_URLS
    assert "Mozilla/5.0" in BINANCE_HEADERS["User-Agent"]

def test_successful_response_is_reused_from_cache(tmp_path):
    class Session:
        def __init__(self): self.calls=0
        def get(self,url,**kwargs):
            self.calls+=1
            class Response:
                def raise_for_status(self): pass
                def json(self): return {"symbols":[]}
            return Response()
    session=Session()
    client=BinanceClient(session=session,cache_dir=tmp_path)
    assert client.exchange_info()=={"symbols":[]}
    assert client.exchange_info()=={"symbols":[]}
    assert session.calls==1

def test_api_error_payload_falls_back_to_next_host():
    class Session:
        def get(self,url,**kwargs):
            class Response:
                def raise_for_status(self): pass
                def json(self):
                    return {"code":-1,"msg":"blocked"} if "bad" in url else {"symbols":[]}
            return Response()
    assert BinanceClient(session=Session(),base_urls=("https://bad","https://ok")).exchange_info()=={"symbols":[]}
