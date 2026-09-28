from listing_analysis.binance import contracts_from_exchange_info,map_contract

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

