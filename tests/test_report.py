from datetime import date
from decimal import Decimal
from listing_analysis.analysis import analyze_listing
from test_analysis import listing,contract,candle
from listing_analysis.report import render_report,summary
from listing_analysis.cli import write_text
import listing_analysis.cli as cli

def test_escape_and_missing_excluded_from_denominator():
    bad=listing(); object.__setattr__(bad,"notice_id","<script>alert(1)</script>")
    a=analyze_listing(bad,contract(),[candle(1,"2"),candle(8,"3")],date(2025,7,20))
    html=render_report([a],date(2025,7,20),warnings=["<b>bad</b>"])
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;bad&lt;/b&gt;" in html
    stats,_=summary([a]); assert stats[7]["count"]==1 and stats[30]["count"]==0

def test_write_text_creates_pages_output_directory(tmp_path):
    output=tmp_path/"public"/"index.html"
    write_text(output,"<html lang='ko'></html>")
    assert output.read_text(encoding="utf-8")=="<html lang='ko'></html>"

def test_fail_on_collection_error_keeps_previous_report(tmp_path,monkeypatch):
    output=tmp_path/"public"/"index.html"
    write_text(output,"last successful report")
    class FailedUpbit:
        def __init__(self,*args,**kwargs): pass
        def collect(self,*args,**kwargs):
            return type("Result",(),{"errors":["blocked"],"listings":[],"notices_examined":0})()
    class EmptyBinance:
        def __init__(self,*args,**kwargs): pass
        def exchange_info(self): return {"symbols":[]}
    monkeypatch.setattr(cli,"UpbitClient",FailedUpbit)
    monkeypatch.setattr(cli,"BinanceClient",EmptyBinance)
    try:
        cli.main(["--output",str(output),"--fail-on-collection-error"])
    except SystemExit as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("collection failure should exit")
    assert output.read_text(encoding="utf-8")=="last successful report"
