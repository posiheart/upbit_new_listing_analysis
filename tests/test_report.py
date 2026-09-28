from datetime import date
from decimal import Decimal
from listing_analysis.analysis import analyze_listing
from test_analysis import listing,contract,candle
from listing_analysis.report import render_report,summary

def test_escape_and_missing_excluded_from_denominator():
    bad=listing(); object.__setattr__(bad,"notice_id","<script>alert(1)</script>")
    a=analyze_listing(bad,contract(),[candle(1,"2"),candle(8,"3")],date(2025,7,20))
    html=render_report([a],date(2025,7,20),warnings=["<b>bad</b>"])
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;bad&lt;/b&gt;" in html
    stats,_=summary([a]); assert stats[7]["count"]==1 and stats[30]["count"]==0

